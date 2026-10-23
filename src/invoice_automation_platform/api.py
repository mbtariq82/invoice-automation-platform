import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from openai import OpenAI

from .extraction import (
    configured_model,
    create_client,
    extract_invoice,
    extract_pdf_text_from_bytes,
)
from .schemas import Invoice

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

router = APIRouter()


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    try:
        return create_client()
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


@router.post("/v1/invoices/extract", response_model=Invoice)
async def extract_invoice_from_pdf(
    file: Annotated[UploadFile, File(description="PDF invoice to extract")],
    client: Annotated[OpenAI, Depends(get_client)],
    model: Annotated[str, Depends(get_model)],
) -> Invoice:
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
        return await run_in_threadpool(extract_invoice, client, model, text)
    except Exception as exc:
        logger.exception("Invoice extraction failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invoice extraction failed",
        ) from exc


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
