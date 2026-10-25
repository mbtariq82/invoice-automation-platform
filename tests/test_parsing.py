import json
from datetime import date
from decimal import Decimal

import pytest

from invoice_automation_platform.extraction import parse_invoice
from invoice_automation_platform.extraction.normalization import normalize_invoice_payload


def test_normalize_invoice_payload_maps_aliases_and_drops_extras() -> None:
    payload = {
        "vendor_name": "Acme Industrial Supply Co",
        "invoice_number": "ACM-100145",
        "date": "2024-03-12",
        "po_number": "PO-55210",
        "billing_address": "Chicago, IL",
        "currency": "usd",
        "line_items": [
            {
                "description": "Industrial grade bolts",
                "quantity": 4,
                "unit_price": 48.5,
                "amount": 194.0,
            }
        ],
        "subtotal": 346.5,
        "tax": 25.99,
        "total_amount": 372.49,
        "document_type": "Invoice",
    }

    normalized = normalize_invoice_payload(payload)

    assert "po_number" not in normalized
    assert "billing_address" not in normalized
    assert normalized["invoice_date"] == "2024-03-12"
    assert normalized["invoice_number"] == "ACM-100145"
    assert normalized["currency"] == "USD"
    assert normalized["total"] == 372.49
    assert normalized["document_type"] == "invoice"
    assert normalized["lines"] == [
        {"description": "Industrial grade bolts", "amount": 194.0}
    ]


def test_parse_invoice_accepts_model_field_drift() -> None:
    content = json.dumps(
        {
            "vendor_name": "Acme Industrial Supply Co",
            "invoice_number": "ACM-100145",
            "date": "2024-03-12",
            "line_items": [
                {
                    "description": "Industrial grade bolts",
                    "quantity": 4,
                    "unit_price": 48.5,
                    "amount": 194.0,
                }
            ],
            "subtotal": 194.0,
            "tax": 16.98,
            "total_amount": 210.98,
            "document_type": "invoice",
        }
    )

    invoice = parse_invoice(content)

    assert invoice.vendor_name == "Acme Industrial Supply Co"
    assert invoice.invoice_date == date(2024, 3, 12)
    assert invoice.due_date is None
    assert invoice.currency is None
    assert invoice.total == Decimal("210.98")
    assert invoice.lines[0].amount == Decimal("194.0")


def test_parse_invoice_accepts_credit_note_aliases() -> None:
    content = json.dumps(
        {
            "vendor_name": "Suidkus Packaging",
            "invoice_number": "CN-2026-0933",
            "total": 100,
            "document_type": "Credit Note",
            "items": [
                {
                    "description": "Stretch wrap",
                    "line_total": 100,
                }
            ],
        }
    )

    invoice = parse_invoice(content)

    assert invoice.document_type == "credit_note"
    assert invoice.lines[0].amount == Decimal("100")


def test_parse_invoice_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_invoice("{not json")
