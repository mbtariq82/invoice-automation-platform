import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import importlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.auth import crypt, jwt

from invoice_automation_platform.api import auth

AUDIENCE = "https://invoice-test.run.app"


@pytest.fixture
def signed_token(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    signer = crypt.RSASigner.from_string(private, key_id="test-key")
    monkeypatch.setenv("API_TOKEN_AUDIENCES", AUDIENCE)
    monkeypatch.setenv("API_ALLOWED_MEMBERS", "user:alice@example.com,user:bob@example.com")
    monkeypatch.delenv("API_ADMIN_SUBJECTS", raising=False)
    monkeypatch.setattr(auth, "_certificate_request", lambda *args, **kwargs: SimpleNamespace(status=200, data=json.dumps({"test-key": public}).encode()))

    def mint(**overrides):
        now = int(time.time())
        claims = dict(iss="https://accounts.google.com", aud=AUDIENCE, sub="alice-subject", email="alice@example.com", email_verified=True, iat=now, exp=now + 300)
        claims.update(overrides)
        return jwt.encode(signer, claims).decode()

    return mint


def test_signed_identity_ignores_spoofed_headers(signed_token):
    principal = auth.get_current_principal({
        "authorization": f"Bearer {signed_token()}",
        "x-goog-authenticated-user-id": "admin-subject",
        "x-goog-authenticated-user-email": "admin@example.com",
    })
    assert principal == auth.Principal("alice-subject", "alice@example.com")


@pytest.mark.parametrize("overrides", [
    {"aud": "https://other.run.app"}, {"exp": 1},
    {"iss": "https://attacker.example.com"}, {"sub": ""},
])
def test_invalid_claims_are_rejected(signed_token, overrides):
    with pytest.raises(HTTPException) as error:
        auth.get_current_principal({"authorization": f"Bearer {signed_token(**overrides)}"})
    assert error.value.status_code == 401


def test_signature_tampering_is_rejected(signed_token):
    token = signed_token()
    head, payload, signature = token.split(".")
    replacement = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(HTTPException) as error:
        auth.get_current_principal({"authorization": f"Bearer {head}.{payload}.{replacement}"})
    assert error.value.status_code == 401


def test_spoofed_identity_without_token_is_rejected():
    with pytest.raises(HTTPException) as error:
        auth.get_current_principal({"x-goog-authenticated-user-email": "admin@example.com"})
    assert error.value.status_code == 401


@pytest.mark.parametrize("claims", [{"email_verified": False}, {"email": "outsider@example.com"}])
def test_unverified_or_unlisted_email_is_denied(signed_token, claims):
    with pytest.raises(HTTPException) as error:
        auth.get_current_principal({"authorization": f"Bearer {signed_token(**claims)}"})
    assert error.value.status_code == 403


def test_admin_configuration_matches_verified_email(signed_token, monkeypatch):
    monkeypatch.setenv("API_ADMIN_SUBJECTS", "user:alice@example.com")
    principal = auth.get_current_principal({"authorization": f"Bearer {signed_token()}"})
    assert auth.is_admin(principal)


def test_protected_route_rejects_spoofing_and_accepts_signed_token(signed_token, monkeypatch):
    api = importlib.import_module("invoice_automation_platform.api.app")
    monkeypatch.setattr(api, "initialize_database", AsyncMock())
    listing = AsyncMock(return_value=[])
    monkeypatch.setattr(api.repository, "list_invoices", listing)
    app = api.create_app()
    app.dependency_overrides[api.get_db] = lambda: object()
    with TestClient(app) as client:
        assert client.get("/v1/invoices", headers={"X-Goog-Authenticated-User-Email": "admin@example.com"}).status_code == 401
        listing.assert_not_awaited()
        response = client.get("/v1/invoices", headers={"Authorization": f"Bearer {signed_token()}"})
        assert response.status_code == 200
        assert listing.call_args.kwargs["created_by"] == "alice-subject"
