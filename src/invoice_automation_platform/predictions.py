from datetime import date
from decimal import Decimal
from typing import Any

from .schemas import Invoice


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def invoice_to_prediction(invoice: Invoice) -> dict[str, Any]:
    return {
        "vendor_name": invoice.vendor_name,
        "invoice_number": invoice.invoice_number,
        "invoice_date": _date(invoice.invoice_date),
        "due_date": _date(invoice.due_date),
        "currency": invoice.currency,
        "subtotal": _money(invoice.subtotal),
        "tax": _money(invoice.tax),
        "total_amount": _money(invoice.total),
        "document_type": invoice.document_type,
        "line_items": [
            {"description": line.description, "amount": _money(line.amount)}
            for line in invoice.lines
        ],
        "flagged": False,
        "references": [],
    }
