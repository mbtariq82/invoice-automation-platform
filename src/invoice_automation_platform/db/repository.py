import hashlib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import InvoiceRecord
from ..invoices.schemas import Invoice, InvoiceLine


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def get_by_content_hash(session: AsyncSession, content_hash: str, *, created_by: str | None = None) -> InvoiceRecord | None:
    statement = select(InvoiceRecord).where(InvoiceRecord.content_hash == content_hash)
    if created_by is not None:
        statement = statement.where(InvoiceRecord.created_by == created_by)
    return await session.scalar(statement)


async def get_by_id(session: AsyncSession, record_id: int, *, created_by: str | None = None) -> InvoiceRecord | None:
    statement = select(InvoiceRecord).where(InvoiceRecord.id == record_id)
    if created_by is not None:
        statement = statement.where(InvoiceRecord.created_by == created_by)
    return await session.scalar(statement)


async def list_invoices(
    session: AsyncSession, *, limit: int = 20, offset: int = 0, created_by: str | None = None
) -> list[InvoiceRecord]:
    statement = select(InvoiceRecord)
    if created_by is not None:
        statement = statement.where(InvoiceRecord.created_by == created_by)
    statement = (
        statement.order_by(InvoiceRecord.created_at.desc(), InvoiceRecord.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(statement))


async def create_invoice_record(
    session: AsyncSession,
    *,
    content_hash: str,
    source_filename: str | None,
    invoice: Invoice,
    created_by: str = "legacy",
) -> InvoiceRecord:
    record = InvoiceRecord(
        content_hash=content_hash,
        source_filename=source_filename,
        created_by=created_by,
        vendor_name=invoice.vendor_name,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        document_type=invoice.document_type,
        lines=[
            {"description": line.description, "amount": str(line.amount)}
            for line in invoice.lines
        ],
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


def to_invoice(record: InvoiceRecord) -> Invoice:
    return Invoice(
        vendor_name=record.vendor_name,
        invoice_number=record.invoice_number,
        invoice_date=record.invoice_date,
        due_date=record.due_date,
        currency=record.currency,
        subtotal=record.subtotal,
        tax=record.tax,
        total=record.total,
        document_type=record.document_type,
        lines=[
            InvoiceLine(description=item["description"], amount=Decimal(item["amount"]))
            for item in record.lines
        ],
    )
