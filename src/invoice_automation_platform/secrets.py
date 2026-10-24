import os
import re
from functools import lru_cache
from pathlib import Path

import google_crc32c
from dotenv import load_dotenv
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from google.cloud import secretmanager

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

SECRET_VERSION_PATTERN = re.compile(
    r"projects/[^/\s]+/secrets/[A-Za-z0-9_-]+/versions/[1-9][0-9]*"
)


class SecretConfigurationError(RuntimeError):
    """A secret could not be resolved; messages never contain secret values."""


@lru_cache(maxsize=1)
def _secret_manager_client() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()


@lru_cache(maxsize=8)
def _read_secret_version(resource_name: str) -> str:
    try:
        response = _secret_manager_client().access_secret_version(
            request={"name": resource_name}, timeout=10, retry=None
        )
        data = response.payload.data
        if google_crc32c.value(data) != response.payload.data_crc32c:
            raise SecretConfigurationError("Secret Manager payload integrity check failed.")
        value = data.decode("utf-8")
    except (GoogleAPIError, GoogleAuthError, UnicodeDecodeError):
        raise SecretConfigurationError("Secret Manager value could not be loaded.") from None

    if not value.strip():
        raise SecretConfigurationError("Secret Manager returned an empty value.")
    return value


def get_secret(name: str) -> str:
    """Use an explicit Secret Manager version, or a local environment value.

    A configured secret reference takes precedence and never falls back to a
    local value on failure. No Google credentials are needed in local mode.
    """
    reference = os.getenv(f"{name}_SECRET_VERSION")
    if reference is not None:
        if not SECRET_VERSION_PATTERN.fullmatch(reference):
            raise SecretConfigurationError(
                f"{name}_SECRET_VERSION must be projects/PROJECT/secrets/SECRET/versions/NUMBER."
            )
        return _read_secret_version(reference)

    value = os.environ[name]
    if not value.strip():
        raise SecretConfigurationError(f"{name} is empty.")
    return value
