"""Compatibility exports for runtime secret loading."""
from .config import secrets as _impl
from .config.secrets import *

_read_secret_version = _impl._read_secret_version
_secret_manager_client = _impl._secret_manager_client
secretmanager = _impl.secretmanager
