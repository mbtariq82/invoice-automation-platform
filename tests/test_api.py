from datetime import date
from decimal import Decimal

import pymupdf
import pytest
from fastapi.testclient import TestClient

from invoice_automation_platform import api
from invoice_automation_platform.api import create_app, get_client, get_model
from invoice_automation_platform.extraction import extract_pdf_text_from_bytes
from invoice_automation_platform.schemas import Invoice, InvoiceLine


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
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_client] = lambda: object()
    app.dependency_overrides[get_model] = lambda: "test-model"
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_pdf_returns_invoice(client: TestClient, monkeypatch) -> None:
    def fake_extract_invoice(openai_client, model, text):
        return sample_invoice()

    monkeypatch.setattr(api, "extract_invoice", fake_extract_invoice)

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
    def failing_extract_invoice(openai_client, model, text):
        raise ValueError("upstream failure")

    monkeypatch.setattr(api, "extract_invoice", failing_extract_invoice)

    response = client.post(
        "/v1/invoices/extract",
        files={"file": ("invoice.pdf", make_pdf("Acme invoice"), "application/pdf")},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Invoice extraction failed"


def test_extract_pdf_text_from_bytes() -> None:
    text = extract_pdf_text_from_bytes(make_pdf("Invoice ACM-100145"))

    assert "Invoice ACM-100145" in text
