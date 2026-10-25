from typing import Any

TOP_LEVEL_ALIASES: dict[str, tuple[str, ...]] = {
    "vendor_name": ("vendor_name", "vendor", "supplier_name", "supplier"),
    "invoice_number": ("invoice_number", "invoice_no", "invoiceNo", "number"),
    "invoice_date": ("invoice_date", "invoiceDate", "date"),
    "due_date": ("due_date", "dueDate", "payment_due_date"),
    "currency": ("currency", "currency_code"),
    "subtotal": ("subtotal", "sub_total", "net_amount"),
    "tax": ("tax", "tax_amount", "vat", "vat_amount"),
    "total": ("total", "total_amount", "amount_due", "grand_total"),
    "document_type": ("document_type", "documentType", "type"),
}

LINE_ALIASES: dict[str, tuple[str, ...]] = {
    "description": ("description", "desc", "item", "name"),
    "amount": ("amount", "line_total", "line_amount", "total"),
}

CREDIT_TYPES = {"credit", "credit_note", "credit_memo", "creditnote"}


def _first(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _currency(value: Any) -> str | None:
    text = _text(value)
    return None if text is None else text.upper()


def _document_type(value: Any) -> str:
    text = str(value or "invoice").strip().lower().replace("-", "_").replace(" ", "_")
    return "credit_note" if text in CREDIT_TYPES else "invoice"


def _lines(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized = []
    for line in value:
        if not isinstance(line, dict):
            continue
        amount = _first(line, LINE_ALIASES["amount"])
        if amount is None:
            continue
        normalized.append(
            {
                "description": _text(_first(line, LINE_ALIASES["description"])) or "",
                "amount": amount,
            }
        )
    return normalized


def normalize_invoice_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("The model response must be a JSON object")

    normalized = {
        field: _first(payload, aliases)
        for field, aliases in TOP_LEVEL_ALIASES.items()
    }
    normalized["vendor_name"] = _text(normalized["vendor_name"])
    normalized["invoice_number"] = _text(normalized["invoice_number"])
    normalized["currency"] = _currency(normalized["currency"])
    normalized["document_type"] = _document_type(normalized["document_type"])
    normalized["lines"] = _lines(_first(payload, ("lines", "line_items", "items")))
    return normalized
