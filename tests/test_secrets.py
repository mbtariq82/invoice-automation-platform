from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import google_crc32c
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound, PermissionDenied
from google.auth.exceptions import DefaultCredentialsError

from invoice_automation_platform import api, db, extraction
from invoice_automation_platform.config import secrets

VERSION = "projects/example-project/secrets/example-secret/versions/1"


def response_for(data: bytes, *, checksum: int | None = None):
    return SimpleNamespace(
        payload=SimpleNamespace(
            data=data,
            data_crc32c=google_crc32c.value(data) if checksum is None else checksum,
        )
    )


@pytest.fixture(autouse=True)
def isolated_secret_settings(monkeypatch):
    for name in ("DATABASE_URL", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    secrets._read_secret_version.cache_clear()
    secrets._secret_manager_client.cache_clear()
    yield
    secrets._read_secret_version.cache_clear()
    secrets._secret_manager_client.cache_clear()


@pytest.fixture
def secret_client(monkeypatch):
    client = Mock()
    client.access_secret_version.return_value = response_for(b"cloud-value")
    monkeypatch.setattr(secrets.secretmanager, "SecretManagerServiceClient", lambda: client)
    return client


def test_local_settings_do_not_require_google_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://local/local")
    factory = Mock(side_effect=AssertionError("Google must not be contacted"))
    monkeypatch.setattr(secrets.secretmanager, "SecretManagerServiceClient", factory)

    assert db.database_url() == "postgresql+psycopg://local/local"
    factory.assert_not_called()


def test_missing_local_secret_keeps_configuration_error():
    with pytest.raises(KeyError, match="OPENROUTER_API_KEY"):
        secrets.get_secret("OPENROUTER_API_KEY")


def test_empty_local_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "  ")
    with pytest.raises(secrets.SecretConfigurationError, match="is empty"):
        secrets.get_secret("OPENROUTER_API_KEY")


def test_cloud_reference_takes_precedence_and_is_cached(monkeypatch, secret_client):
    monkeypatch.setenv("OPENROUTER_API_KEY", "local-value")
    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", VERSION)

    assert secrets.get_secret("OPENROUTER_API_KEY") == "cloud-value"
    assert secrets.get_secret("OPENROUTER_API_KEY") == "cloud-value"
    secret_client.access_secret_version.assert_called_once_with(
        request={"name": VERSION}, timeout=10, retry=None
    )


def test_new_version_fetches_a_new_value(monkeypatch, secret_client):
    secret_client.access_secret_version.side_effect = [
        response_for(b"first-value"), response_for(b"second-value")
    ]
    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", VERSION)
    assert secrets.get_secret("OPENROUTER_API_KEY") == "first-value"

    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", VERSION[:-1] + "2")
    assert secrets.get_secret("OPENROUTER_API_KEY") == "second-value"
    assert secret_client.access_secret_version.call_count == 2


@pytest.mark.parametrize(
    "reference", ["", "example-secret", VERSION[:-1] + "latest", VERSION[:-1] + "0"]
)
def test_invalid_reference_never_falls_back(monkeypatch, secret_client, reference):
    monkeypatch.setenv("OPENROUTER_API_KEY", "local-value")
    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", reference)

    with pytest.raises(secrets.SecretConfigurationError, match="must be"):
        secrets.get_secret("OPENROUTER_API_KEY")
    secret_client.access_secret_version.assert_not_called()


@pytest.mark.parametrize("error", [PermissionDenied, NotFound, DefaultCredentialsError])
def test_failed_reads_are_sanitized_and_not_cached(monkeypatch, secret_client, error):
    monkeypatch.setenv("OPENROUTER_API_KEY", "local-value")
    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", VERSION)
    secret_client.access_secret_version.side_effect = [
        error("sensitive provider details"), response_for(b"recovered-value")
    ]

    with pytest.raises(secrets.SecretConfigurationError) as raised:
        secrets.get_secret("OPENROUTER_API_KEY")
    assert "sensitive provider details" not in str(raised.value)
    assert raised.value.__suppress_context__
    assert secrets.get_secret("OPENROUTER_API_KEY") == "recovered-value"
    assert secret_client.access_secret_version.call_count == 2


@pytest.mark.parametrize(
    "response",
    [
        response_for(b"secret-value", checksum=0),
        response_for(b"\xff"),
        response_for(b""),
        response_for(b"   "),
    ],
)
def test_corrupt_or_empty_payload_is_rejected(monkeypatch, secret_client, response):
    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", VERSION)
    secret_client.access_secret_version.return_value = response

    with pytest.raises(secrets.SecretConfigurationError) as raised:
        secrets.get_secret("OPENROUTER_API_KEY")
    assert "secret-value" not in str(raised.value)


def test_database_and_model_client_use_the_secret_resolver(monkeypatch, secret_client):
    monkeypatch.setenv("DATABASE_URL_SECRET_VERSION", VERSION)
    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", VERSION)

    assert db.database_url() == "cloud-value"
    client = extraction.create_client(timeout=12)
    try:
        assert client.api_key == "cloud-value"
    finally:
        client.close()
    assert secret_client.access_secret_version.call_count == 1


def test_health_check_does_not_access_model_secrets(monkeypatch):
    import importlib
    api_module = importlib.import_module("invoice_automation_platform.api.app")
    initialize = AsyncMock()
    monkeypatch.setattr(api_module, "initialize_database", initialize)
    monkeypatch.setenv("DATABASE_URL_SECRET_VERSION", VERSION)
    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", VERSION)
    factory = Mock(side_effect=AssertionError("Health must not fetch secrets"))
    monkeypatch.setattr(secrets.secretmanager, "SecretManagerServiceClient", factory)

    with TestClient(api.create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
    factory.assert_not_called()
    initialize.assert_awaited_once()


def test_api_returns_a_safe_error_when_credentials_cannot_be_loaded(
    monkeypatch, secret_client
):
    monkeypatch.setenv("OPENROUTER_API_KEY_SECRET_VERSION", VERSION)
    secret_client.access_secret_version.side_effect = PermissionDenied(
        "sensitive provider details"
    )

    with pytest.raises(HTTPException) as raised:
        api.get_client.__wrapped__()
    assert raised.value.status_code == 503
    assert raised.value.detail == "OpenRouter credentials could not be loaded"


def test_alembic_can_load_its_database_url_from_secret_manager(
    monkeypatch, secret_client, capsys
):
    monkeypatch.setenv("DATABASE_URL_SECRET_VERSION", VERSION)
    secret_client.access_secret_version.return_value = response_for(
        b"postgresql+psycopg://invoice_app:p%40ss%25word@/invoices"
        b"?host=/cloudsql/example-project:europe-west2:invoice-dev-postgres"
    )

    command.upgrade(Config("alembic.ini"), "head", sql=True)

    assert "CREATE TABLE invoice_records" in capsys.readouterr().out
