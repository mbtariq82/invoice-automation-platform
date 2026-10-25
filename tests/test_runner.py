from decimal import Decimal
from pathlib import Path

from invoice_automation_platform.evaluation import runner
from invoice_automation_platform.evaluation import runner as evaluation_runner
from invoice_automation_platform.evaluation.runner import select_documents
from invoice_automation_platform.invoices.schemas import Invoice

DOCUMENTS = [
    {"doc_id": "clean-a", "category": "clean", "render": "pdf", "file": "a.pdf"},
    {"doc_id": "clean-b", "category": "clean", "render": "pdf", "file": "b.pdf"},
    {"doc_id": "photo-a", "category": "photo", "render": "jpeg", "file": "a.jpg"},
    {"doc_id": "scan-a", "category": "scan", "render": "png", "file": "a.png"},
]


def test_select_documents_keeps_only_pdfs() -> None:
    assert [document["doc_id"] for document in select_documents(DOCUMENTS)] == [
        "clean-a",
        "clean-b",
    ]


def test_select_documents_filters_category_and_limit() -> None:
    selected = select_documents(DOCUMENTS, category="clean", limit=1)
    assert [document["doc_id"] for document in selected] == ["clean-a"]


def test_select_documents_filters_by_doc_id() -> None:
    selected = select_documents(DOCUMENTS, doc_id="clean-b")
    assert [document["doc_id"] for document in selected] == ["clean-b"]


def test_extract_one_retries_transient_failures(monkeypatch) -> None:
    calls = []

    def fake_extract_invoice(client, model, text):
        calls.append(text)
        if len(calls) < 3:
            raise ValueError("empty response")
        return Invoice(
            vendor_name="Acme Industrial Supply Co",
            invoice_number="ACM-100145",
            total=Decimal("372.49"),
            document_type="invoice",
        )

    monkeypatch.setattr(evaluation_runner, "extract_pdf_text", lambda path: "text")
    monkeypatch.setattr(evaluation_runner, "extract_invoice", fake_extract_invoice)
    monkeypatch.setattr(evaluation_runner.time, "sleep", lambda seconds: None)

    doc_id, prediction, error = evaluation_runner._extract_one(
        {"doc_id": "clean-a", "file": "a.pdf"},
        Path("."),
        object(),
        "model",
        retries=2,
    )

    assert doc_id == "clean-a"
    assert error is None
    assert len(calls) == 3
    assert prediction is not None
    assert prediction["vendor_name"] == "Acme Industrial Supply Co"
