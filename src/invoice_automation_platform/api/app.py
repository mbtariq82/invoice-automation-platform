import logging
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
from openai import AsyncOpenAI
from pydantic import ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repository
from ..db.session import close_database, get_db, initialize_database
from ..extraction import (
    configured_model,
    create_async_client,
    extract_invoice_async,
    extract_pdf_text_from_bytes,
)

# Kept as a module-level seam so API tests and integrations can replace the
# model call without touching the extraction package.
extract_invoice = extract_invoice_async
from ..db.models import InvoiceRecord
from ..invoices.schemas import Invoice
from ..config.secrets import SecretConfigurationError
from ..invoices.validation import TotalsCheck, check_invoice_totals
from .auth import Principal, get_current_principal, is_admin

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def _record_fields(record: InvoiceRecord) -> dict[str, Any]:
    invoice = repository.to_invoice(record)
    return {
        "id": record.id,
        "source_filename": record.source_filename,
        "created_by": record.created_by,
        "created_at": record.created_at,
        **invoice.model_dump(),
        "totals_check": check_invoice_totals(invoice),
    }


class InvoiceRecordResponse(Invoice):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_filename: str | None
    created_by: str | None
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
def get_client() -> AsyncOpenAI:
    try:
        return create_async_client()
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


def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    return get_current_principal(dict(request.headers))


@router.post("/v1/invoices/extract", response_model=ExtractInvoiceResponse)
async def extract_invoice_from_pdf(
    file: Annotated[UploadFile, File(description="PDF invoice to extract")],
    client: Annotated[AsyncOpenAI, Depends(get_client)],
    model: Annotated[str, Depends(get_model)],
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(current_principal)],
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
    owner = None if is_admin(principal) else principal.subject
    existing = await repository.get_by_content_hash(db, content_hash, created_by=owner)
    if existing is not None:
        return ExtractInvoiceResponse.from_record(existing, cached=True)

    try:
        text = await run_in_threadpool(extract_pdf_text_from_bytes, data)
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
        invoice = await extract_invoice(client, model, text)
    except Exception as exc:
        logger.exception("Invoice extraction failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invoice extraction failed",
        ) from exc

    record = await repository.create_invoice_record(
        db,
        content_hash=content_hash,
        source_filename=file.filename,
        created_by=principal.subject,
        invoice=invoice,
    )
    return ExtractInvoiceResponse.from_record(record, cached=False)


@router.get("/v1/invoices", response_model=list[InvoiceRecordResponse])
async def list_invoices_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(current_principal)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InvoiceRecordResponse]:
    owner = None if is_admin(principal) else principal.subject
    records = await repository.list_invoices(db, limit=limit, offset=offset, created_by=owner)
    return [InvoiceRecordResponse.from_record(record) for record in records]


@router.get("/v1/invoices/{invoice_id}", response_model=InvoiceRecordResponse)
async def get_invoice_endpoint(
    invoice_id: int, db: Annotated[AsyncSession, Depends(get_db)], principal: Annotated[Principal, Depends(current_principal)]
) -> InvoiceRecordResponse:
    owner = None if is_admin(principal) else principal.subject
    record = await repository.get_by_id(db, invoice_id, created_by=owner)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        )
    return InvoiceRecordResponse.from_record(record)


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        await initialize_database()
        yield
    finally:
        try:
            if get_client.cache_info().currsize:
                await get_client().close()
                get_client.cache_clear()
        finally:
            await close_database()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Invoice Automation Platform",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "invoice_automation_platform.api:app",
        host="0.0.0.0",
        port=8000,
        loop="invoice_automation_platform.api.event_loop:loop_factory",
    )


if __name__ == "__main__":
    run()
