from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InvoiceRecord(Base):
    __tablename__ = "invoice_records"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_invoice_records_content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_filename: Mapped[str | None] = mapped_column(String(255))
    vendor_name: Mapped[str] = mapped_column(String)
    invoice_number: Mapped[str | None] = mapped_column(String)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    document_type: Mapped[str] = mapped_column(String(20))
    lines: Mapped[list[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
