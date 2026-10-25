import os

from google.cloud import storage


def archive_invoice_pdf(data: bytes, *, content_hash: str, source_filename: str | None) -> str:
    bucket_name = os.environ.get("INVOICE_BUCKET")
    if not bucket_name or not bucket_name.strip():
        raise RuntimeError("INVOICE_BUCKET is not configured")

    object_name = f"invoices/{content_hash}.pdf"
    blob = storage.Client().bucket(bucket_name).blob(object_name)
    metadata = {"content_hash": content_hash}
    if source_filename:
        metadata["source_filename"] = source_filename[:256]
    blob.metadata = metadata
    blob.upload_from_string(data, content_type="application/pdf", timeout=60)
    return object_name
