import os
from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import HTTPException, status


@dataclass(frozen=True)
class Principal:
    subject: str
    email: str | None = None


def _admin_subjects() -> frozenset[str]:
    return frozenset(item.strip() for item in os.getenv("API_ADMIN_SUBJECTS", "").split(",") if item.strip())


def get_current_principal(headers: dict[str, str]) -> Principal:
    raw = headers.get("x-goog-authenticated-user-id") or headers.get("x-goog-authenticated-user-email")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    value = unquote(raw)
    subject = value.split(":", 1)[-1].strip()
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticated identity")
    email_raw = headers.get("x-goog-authenticated-user-email")
    email = unquote(email_raw).split(":", 1)[-1].strip() if email_raw else None
    return Principal(subject=subject, email=email)


def is_admin(principal: Principal) -> bool:
    return principal.subject in _admin_subjects() or (principal.email is not None and principal.email in _admin_subjects())
