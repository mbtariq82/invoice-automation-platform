import os
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock

import cachecontrol
import requests
from fastapi import HTTPException
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import id_token

_verification_lock = Lock()


@dataclass(frozen=True)
class Principal:
    subject: str
    email: str | None = None


@lru_cache(maxsize=1)
def _certificate_transport() -> Request:
    # Cache Google's signing certificates according to their HTTP cache headers.
    # Token validation decisions are never cached.
    return Request(session=cachecontrol.CacheControl(requests.Session()))


def _certificate_request(url, method="GET", **kwargs):
    kwargs["timeout"] = 5
    return _certificate_transport()(url=url, method=method, **kwargs)


def _configured_members(name: str) -> set[str]:
    return {item.strip() for item in os.getenv(name, "").split(",") if item.strip()}


def _matches(principal: Principal, members: set[str]) -> bool:
    if f"subject:{principal.subject}" in members or principal.subject in members:
        return True
    return principal.email is not None and bool(
        {principal.email, f"user:{principal.email}", f"serviceAccount:{principal.email}"} & members
    )


def get_current_principal(headers: dict[str, str]) -> Principal:
    # A dedicated header preserves the signed token across Cloud Run's IAM
    # proxy, which can modify the standard authorization headers.
    # API Gateway may replace Authorization with its Cloud Run identity token;
    # ESPv2 preserves the browser token in X-Forwarded-Authorization.
    authorization = headers.get(
        "x-api-authorization",
        headers.get("x-forwarded-authorization", headers.get("authorization", "")),
    )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    audiences = sorted(_configured_members("API_TOKEN_AUDIENCES"))
    members = _configured_members("API_ALLOWED_MEMBERS")
    if not audiences or not members:
        raise HTTPException(503, "Authentication is not configured")
    try:
        # FastAPI runs this synchronous dependency off the event loop.
        with _verification_lock:
            claims = id_token.verify_oauth2_token(
                token.strip(), _certificate_request, audience=audiences
            )
    except TransportError:
        raise HTTPException(503, "Identity verification is temporarily unavailable") from None
    except (ValueError, GoogleAuthError):
        raise HTTPException(401, "Invalid identity token", headers={"WWW-Authenticate": "Bearer"}) from None
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise HTTPException(401, "Invalid identity token")
    email = claims.get("email") if claims.get("email_verified") is True else None
    if email is not None and not isinstance(email, str):
        raise HTTPException(401, "Invalid identity token")
    principal = Principal(subject=subject, email=email)
    if not _matches(principal, members):
        raise HTTPException(403, "Caller is not allowed to access the API")
    return principal


def is_admin(principal: Principal) -> bool:
    return _matches(principal, _configured_members("API_ADMIN_SUBJECTS"))
