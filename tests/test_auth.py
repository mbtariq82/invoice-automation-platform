import pytest
from fastapi import HTTPException

from invoice_automation_platform.api.auth import get_current_principal, is_admin


def test_principal_decodes_cloud_run_identity_headers() -> None:
    principal = get_current_principal(
        {
            "x-goog-authenticated-user-id": "accounts.google.com%3Aalice-subject",
            "x-goog-authenticated-user-email": "accounts.google.com%3Aalice%40example.com",
        }
    )

    assert principal.subject == "alice-subject"
    assert principal.email == "alice@example.com"


def test_missing_identity_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        get_current_principal({})

    assert error.value.status_code == 401


def test_admin_membership_can_be_configured(monkeypatch) -> None:
    principal = get_current_principal(
        {"x-goog-authenticated-user-id": "accounts.google.com%3Aadmin-subject"}
    )
    monkeypatch.setenv("API_ADMIN_SUBJECTS", "admin-subject")

    assert is_admin(principal)
