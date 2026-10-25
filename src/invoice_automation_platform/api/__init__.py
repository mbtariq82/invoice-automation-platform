"""HTTP API package and backwards-compatible public entry points."""

from .app import app, create_app, get_client, get_db, get_model
from ..extraction import extract_invoice, extract_pdf_text_from_bytes

__all__ = ["app", "create_app", "get_client", "get_db", "get_model"]

if __name__ == "__main__":
    from .app import run

    run()
