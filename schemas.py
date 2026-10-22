
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    amount: Decimal


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_name: str
    invoice_number: str
    invoice_date: date | None
    due_date: date | None
    currency: str
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal
    document_type: Literal["invoice", "credit_note"]
    lines: list[InvoiceLine]
