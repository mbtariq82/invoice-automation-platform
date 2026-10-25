from datetime import date
from decimal import Decimal

import pymupdf
import pytest
from fastapi.testclient import TestClient

from invoice_automation_platform import api
import importlib
import os
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

api_app = importlib.import_module("invoice_automation_platform.api.app")
from invoice_automation_platform.api import create_app, get_client, get_db, get_model
from invoice_automation_platform.extraction import extract_pdf_text_from_bytes
from invoice_automation_platform.invoices.schemas import Invoice, InvoiceLine
from invoice_automation_platform.api.auth import Principal


def make_pdf(text: str = "") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


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


@pytest.fixture
def client(test_engine, monkeypatch) -> TestClient:
    monkeypatch.setattr(api_app, "initialize_database", AsyncMock())
    app = create_app()
    app.dependency_overrides[get_client] = lambda: object()
    app.dependency_overrides[get_model] = lambda: "test-model"
    app.dependency_overrides[api_app.current_principal] = lambda: Principal("alice-subject", "alice@example.com")
    with TestClient(
        app,
    ) as test_client:
        async def open_test_session():
            engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
            connection = await engine.connect()
            transaction = await connection.begin()
            session = async_sessionmaker(bind=connection, expire_on_commit=False)()
            return engine, connection, transaction, session

        engine, connection, transaction, session = test_client.portal.call(open_test_session)

        async def override_db():
            yield session

        app.dependency_overrides[get_db] = override_db
        try:
            yield test_client
        finally:
            async def close_test_session():
                await session.close()
                await transaction.rollback()
                await connection.close()
                await engine.dispose()

            test_client.portal.call(close_test_session)


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_pdf_returns_invoice(client: TestClient, monkeypatch) -> None:
    async def fake_extract_invoice(openai_client, model, text):
        return sample_invoice()

    monkeypatch.setattr(api_app, "extract_invoice", fake_extract_invoice)

    response = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", make_pdf("Acme invoice"), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["vendor_name"] == "Acme Industrial Supply Co"
    assert body["invoice_number"] == "ACM-100145"
    assert body["document_type"] == "invoice"
    assert Decimal(str(body["total"])) == Decimal("110.00")
    assert body["lines"][0]["description"] == "Widget"
    assert body["cached"] is False
    assert isinstance(body["id"], int)
    assert body["source_filename"] == "invoice.pdf"


def test_extract_is_idempotent_for_the_same_pdf(client: TestClient, monkeypatch) -> None:
    calls = []

    async def fake_extract_invoice(openai_client, model, text):
        calls.append(text)
        return sample_invoice()

    monkeypatch.setattr(api_app, "extract_invoice", fake_extract_invoice)
    pdf_bytes = make_pdf("Acme invoice")

    first = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
    )
    second = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
    )

    assert len(calls) == 1
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["id"] == second.json()["id"]


def test_list_and_get_invoice(client: TestClient, monkeypatch) -> None:
    async def fake_extract_invoice(client, model, text):
        return sample_invoice()

    monkeypatch.setattr(api_app, "extract_invoice", fake_extract_invoice)

    created = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", make_pdf("Acme invoice"), "application/pdf")},
    ).json()

    listed = client.get("/v1/invoices")
    assert listed.status_code == 200
    assert any(item["id"] == created["id"] for item in listed.json())

    fetched = client.get(f"/v1/invoices/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["vendor_name"] == "Acme Industrial Supply Co"

    missing = client.get("/v1/invoices/999999999")
    assert missing.status_code == 404


@pytest.mark.parametrize(
    "tax,total,expected_status",
    [
        (Decimal("10.00"), Decimal("110.00"), "matched"),
        (Decimal("10.00"), Decimal("125.00"), "mismatch"),
        (None, Decimal("110.00"), "not_checked"),
    ],
)
def test_totals_check_is_consistent_across_api_responses(
    client: TestClient, monkeypatch, tax, total, expected_status
) -> None:
    invoice = sample_invoice().model_copy(update={"tax": tax, "total": total})
    calls = []

    async def fake_extract_invoice(openai_client, model, text):
        calls.append(text)
        return invoice

    monkeypatch.setattr(api_app, "extract_invoice", fake_extract_invoice)
    pdf_bytes = make_pdf("Acme invoice")
    files = {"file": ("invoice.pdf", pdf_bytes, "application/pdf")}

    created = client.post("/v1/invoices/extract", files=files)
    assert created.status_code == 200
    body = created.json()
    check = body["totals_check"]
    assert check["status"] == expected_status
    assert Decimal(body["total"]) == total

    cached = client.post("/v1/invoices/extract", files=files)
    assert cached.status_code == 200
    assert cached.json()["cached"] is True
    assert cached.json()["totals_check"] == check
    assert len(calls) == 1

    fetched = client.get(f"/v1/invoices/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["totals_check"] == check

    listed = client.get("/v1/invoices")
    assert listed.status_code == 200
    stored = next(item for item in listed.json() if item["id"] == body["id"])
    assert stored["totals_check"] == check


def test_extract_rejects_non_pdf_content_type(client: TestClient) -> None:
    response = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Only PDF uploads are supported"


def test_extract_rejects_empty_upload(client: TestClient) -> None:
    response = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_extract_rejects_file_without_pdf_header(client: TestClient) -> None:
    response = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Uploaded file is not a PDF"


def test_extract_rejects_pdf_without_text(client: TestClient) -> None:
    response = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", make_pdf(), "application/pdf")},
    )

    assert response.status_code == 422
    assert "No extractable text" in response.json()["detail"]


def test_extract_returns_bad_gateway_on_model_failure(
    client: TestClient, monkeypatch
) -> None:
    async def failing_extract_invoice(openai_client, model, text):
        raise ValueError("upstream failure")

    monkeypatch.setattr(api_app, "extract_invoice", failing_extract_invoice)

    response = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", make_pdf("Acme invoice"), "application/pdf")},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Invoice extraction failed"


def test_extract_pdf_text_from_bytes() -> None:
    text = extract_pdf_text_from_bytes(make_pdf("Invoice ACM-100145"))

    assert "Invoice ACM-100145" in text
