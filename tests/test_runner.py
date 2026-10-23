from invoice_automation_platform.runner import select_documents

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
