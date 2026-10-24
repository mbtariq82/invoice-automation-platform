import logging
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from openai import OpenAI
from pydantic import ConfigDict
from sqlalchemy.orm import Session

from . import repository
from .db import get_db
from .extraction import (
    configured_model,
    create_client,
    extract_invoice,
    extract_pdf_text_from_bytes,
)
from .models import InvoiceRecord
from .schemas import Invoice
from .secrets import SecretConfigurationError
from .validation import TotalsCheck, check_invoice_totals

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

router = APIRouter()


def _record_fields(record: InvoiceRecord) -> dict[str, Any]:
    invoice = repository.to_invoice(record)
    return {
        "id": record.id,
        "source_filename": record.source_filename,
        "created_at": record.created_at,
        **invoice.model_dump(),
        "totals_check": check_invoice_totals(invoice),
    }


class InvoiceRecordResponse(Invoice):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_filename: str | None
    created_at: datetime
    totals_check: TotalsCheck

    @classmethod
    def from_record(cls, record: InvoiceRecord) -> "InvoiceRecordResponse":
        return cls(**_record_fields(record))


class ExtractInvoiceResponse(InvoiceRecordResponse):
    cached: bool

    @classmethod
    def from_record(cls, record: InvoiceRecord, *, cached: bool) -> "ExtractInvoiceResponse":
        return cls(cached=cached, **_record_fields(record))


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    try:
        return create_client()
    except SecretConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenRouter credentials could not be loaded",
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENROUTER_API_KEY is not configured",
        ) from exc


@lru_cache(maxsize=1)
def get_model() -> str:
    try:
        return configured_model()
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENROUTER_MODEL is not configured",
        ) from exc


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/invoices/extract", response_model=ExtractInvoiceResponse)
async def extract_invoice_from_pdf(
    file: Annotated[UploadFile, File(description="PDF invoice to extract")],
    client: Annotated[OpenAI, Depends(get_client)],
    model: Annotated[str, Depends(get_model)],
    db: Annotated[Session, Depends(get_db)],
) -> ExtractInvoiceResponse:
    if file.content_type not in PDF_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF uploads are supported",
        )

    data = await file.read(MAX_UPLOAD_BYTES + 1)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF exceeds the 10 MB limit",
        )
    if not data.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded file is not a PDF",
        )

    content_hash = repository.hash_bytes(data)
    existing = repository.get_by_content_hash(db, content_hash)
    if existing is not None:
        return ExtractInvoiceResponse.from_record(existing, cached=True)

    try:
        text = extract_pdf_text_from_bytes(data)
    except Exception as exc:
        logger.exception("Could not read PDF")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not read the PDF",
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No extractable text found; scanned PDFs are not supported yet",
        )

    try:
        invoice = await run_in_threadpool(extract_invoice, client, model, text)
    except Exception as exc:
        logger.exception("Invoice extraction failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invoice extraction failed",
        ) from exc

    record = repository.create_invoice_record(
        db,
        content_hash=content_hash,
        source_filename=file.filename,
        invoice=invoice,
    )
    return ExtractInvoiceResponse.from_record(record, cached=False)


@router.get("/v1/invoices", response_model=list[InvoiceRecordResponse])
def list_invoices_endpoint(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InvoiceRecordResponse]:
    records = repository.list_invoices(db, limit=limit, offset=offset)
    return [InvoiceRecordResponse.from_record(record) for record in records]


@router.get("/v1/invoices/{invoice_id}", response_model=InvoiceRecordResponse)
def get_invoice_endpoint(
    invoice_id: int, db: Annotated[Session, Depends(get_db)]
) -> InvoiceRecordResponse:
    record = repository.get_by_id(db, invoice_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )
    return InvoiceRecordResponse.from_record(record)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Invoice Automation Platform",
        version="0.1.0",
    )
    application.include_router(router)
    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("invoice_automation_platform.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
