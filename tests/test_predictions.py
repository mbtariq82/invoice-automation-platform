from datetime import date
from decimal import Decimal

from invoice_automation_platform.predictions import invoice_to_prediction
from invoice_automation_platform.schemas import Invoice, InvoiceLine


def test_invoice_to_prediction_uses_benchmark_field_names() -> None:
    invoice = Invoice(
        vendor_name="Acme Industrial Supply Co",
        invoice_number="ACM-100145",
        invoice_date=date(2024, 3, 12),
        due_date=None,
        currency="USD",
        subtotal=Decimal("346.50"),
        tax=Decimal("25.99"),
        total=Decimal("372.49"),
        document_type="invoice",
        lines=[
            InvoiceLine(
                description="Industrial grade bolts",
                amount=Decimal("194.00"),
            )
        ],
    )

    prediction = invoice_to_prediction(invoice)

    assert prediction["invoice_date"] == "2024-03-12"
    assert prediction["due_date"] is None
    assert prediction["subtotal"] == 346.5
    assert prediction["tax"] == 25.99
    assert prediction["total_amount"] == 372.49
    assert prediction["line_items"] == [
        {"description": "Industrial grade bolts", "amount": 194.0}
    ]
    assert prediction["flagged"] is False
    assert prediction["references"] == []
