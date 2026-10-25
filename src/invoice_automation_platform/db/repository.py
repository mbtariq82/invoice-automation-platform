import hashlib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import InvoiceRecord
from ..invoices.schemas import Invoice, InvoiceLine


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_by_content_hash(session: Session, content_hash: str) -> InvoiceRecord | None:
    statement = select(InvoiceRecord).where(InvoiceRecord.content_hash == content_hash)
    return session.scalar(statement)


def get_by_id(session: Session, record_id: int) -> InvoiceRecord | None:
    return session.get(InvoiceRecord, record_id)


def list_invoices(
    session: Session, *, limit: int = 20, offset: int = 0
) -> list[InvoiceRecord]:
    statement = (
        select(InvoiceRecord)
        .order_by(InvoiceRecord.created_at.desc(), InvoiceRecord.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def create_invoice_record(
    session: Session,
    *,
    content_hash: str,
    source_filename: str | None,
    invoice: Invoice,
    pdf_object_name: str | None = None,
) -> InvoiceRecord:
    record = InvoiceRecord(
        content_hash=content_hash,
        source_filename=source_filename,
        pdf_object_name=pdf_object_name,
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
    session.commit()
    session.refresh(record)
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
