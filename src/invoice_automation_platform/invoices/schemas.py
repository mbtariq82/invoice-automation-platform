from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    amount: Decimal


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_name: str
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal
    document_type: Literal["invoice", "credit_note"]
    lines: list[InvoiceLine] = Field(default_factory=list)
