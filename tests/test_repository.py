from datetime import date
from decimal import Decimal

from invoice_automation_platform import repository
from invoice_automation_platform.schemas import Invoice, InvoiceLine


def sample_invoice() -> Invoice:
    return Invoice(
        vendor_name="Acme Industrial Supply Co",
        invoice_number="ACM-100145",
        invoice_date=date(2024, 3, 12),
        due_date=None,
        currency="USD",
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        total=Decimal("110.00"),
        document_type="invoice",
        lines=[InvoiceLine(description="Widget", amount=Decimal("100.00"))],
    )


def test_create_and_fetch_by_hash(db_session) -> None:
    record = repository.create_invoice_record(
        db_session,
        content_hash="a" * 64,
        source_filename="invoice.pdf",
        invoice=sample_invoice(),
    )

    assert record.id is not None
    assert record.created_at is not None

    found = repository.get_by_content_hash(db_session, "a" * 64)
    assert found is not None
    assert found.id == record.id

    missing = repository.get_by_content_hash(db_session, "b" * 64)
    assert missing is None


def test_get_by_id(db_session) -> None:
    record = repository.create_invoice_record(
        db_session,
        content_hash="c" * 64,
        source_filename=None,
        invoice=sample_invoice(),
    )

    assert repository.get_by_id(db_session, record.id).id == record.id
    assert repository.get_by_id(db_session, record.id + 1_000_000) is None


def test_list_invoices_orders_newest_first(db_session) -> None:
    first = repository.create_invoice_record(
        db_session,
        content_hash="d" * 64,
        source_filename=None,
        invoice=sample_invoice(),
    )
    second = repository.create_invoice_record(
        db_session,
        content_hash="e" * 64,
        source_filename=None,
        invoice=sample_invoice(),
    )

    records = repository.list_invoices(db_session, limit=10, offset=0)
    ids = [record.id for record in records]

    assert ids.index(second.id) < ids.index(first.id)


def test_to_invoice_round_trips_line_amounts(db_session) -> None:
    record = repository.create_invoice_record(
        db_session,
        content_hash="f" * 64,
        source_filename=None,
        invoice=sample_invoice(),
    )

    invoice = repository.to_invoice(record)

    assert invoice.vendor_name == "Acme Industrial Supply Co"
    assert invoice.lines[0].amount == Decimal("100.00")
    assert invoice.total == Decimal("110.00")
