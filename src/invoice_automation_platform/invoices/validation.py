from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .schemas import Invoice


class TotalsCheck(BaseModel):
    status: Literal["matched", "mismatch", "not_checked"]
    subtotal_plus_tax: Decimal | None = None
    difference: Decimal | None = Field(
        default=None, description="Extracted total minus (subtotal + tax)."
    )
    reason: str | None = None


def check_invoice_totals(invoice: Invoice) -> TotalsCheck:
    """Compare signed header amounts within 0.01 without changing the invoice.

    This is an arithmetic diagnostic, not an invoice approval decision. The
    schema does not yet capture adjustments such as shipping or discounts.
    """
    if invoice.subtotal is None or invoice.tax is None:
        return TotalsCheck(
            status="not_checked",
            reason="Subtotal and tax are both required to compare header totals.",
        )

    subtotal_plus_tax = invoice.subtotal + invoice.tax
    difference = invoice.total - subtotal_plus_tax
    mismatch = abs(difference) > Decimal("0.01")
    return TotalsCheck(
        status="mismatch" if mismatch else "matched",
        subtotal_plus_tax=subtotal_plus_tax,
        difference=difference,
        reason=(
            "Total differs from subtotal plus tax by more than 0.01; "
            "shipping, discounts, or other adjustments may explain the difference."
            if mismatch
            else None
        ),
    )
