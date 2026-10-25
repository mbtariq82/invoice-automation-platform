from decimal import Decimal

import pytest

from invoice_automation_platform.evaluation.predictions import invoice_to_prediction
from invoice_automation_platform.invoices.schemas import Invoice
from invoice_automation_platform.invoices.validation import check_invoice_totals


@pytest.mark.parametrize(
    ("subtotal", "tax", "total", "document_type", "expected_status", "difference"),
    [
        ("100.00", "10.00", "110.00", "invoice", "matched", "0.00"),
        ("100.00", "0.00", "100.00", "invoice", "matched", "0.00"),
        ("0.10", "0.20", "0.30", "invoice", "matched", "0.00"),
        ("100.00", "10.00", "110.01", "invoice", "matched", "0.01"),
        ("100.00", "10.00", "109.99", "invoice", "matched", "-0.01"),
        ("100.00", "10.00", "110.02", "invoice", "mismatch", "0.02"),
        ("100.00", "10.00", "109.98", "invoice", "mismatch", "-0.02"),
        ("-100.00", "-10.00", "-110.00", "credit_note", "matched", "0.00"),
        ("100.00", "10.00", "110.00", "credit_note", "matched", "0.00"),
        ("-100.00", "-10.00", "110.00", "credit_note", "mismatch", "220.00"),
    ],
)
def test_check_invoice_totals(
    subtotal, tax, total, document_type, expected_status, difference
) -> None:
    invoice = Invoice(
        vendor_name="Example supplier",
        subtotal=subtotal,
        tax=tax,
        total=total,
        document_type=document_type,
    )
    original = invoice.model_dump()

    result = check_invoice_totals(invoice)

    assert result.status == expected_status
    assert result.subtotal_plus_tax == Decimal(subtotal) + Decimal(tax)
    assert result.difference == Decimal(difference)
    assert (result.reason is not None) == (expected_status == "mismatch")
    assert invoice.model_dump() == original


@pytest.mark.parametrize("subtotal,tax", [(None, "10.00"), ("100.00", None), (None, None)])
def test_missing_amounts_are_not_checked(subtotal, tax) -> None:
    invoice = Invoice(
        vendor_name="Example supplier",
        subtotal=subtotal,
        tax=tax,
        total="110.00",
        document_type="invoice",
    )

    result = check_invoice_totals(invoice)

    assert result.status == "not_checked"
    assert result.subtotal_plus_tax is None
    assert result.difference is None
    assert result.reason is not None


def test_unmodelled_shipping_is_a_diagnostic_not_an_automatic_flag() -> None:
    invoice = Invoice(
        vendor_name="Example supplier",
        subtotal="100.00",
        tax="10.00",
        total="125.00",  # Includes a printed shipping charge outside this schema.
        document_type="invoice",
    )

    result = check_invoice_totals(invoice)

    assert result.status == "mismatch"
    assert result.difference == Decimal("15.00")
    assert "adjustments may explain" in result.reason
    prediction = invoice_to_prediction(invoice)
    assert prediction["flagged"] is False
    assert prediction["total_amount"] == 125.0
