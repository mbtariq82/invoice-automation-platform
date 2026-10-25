import json
import os
from pathlib import Path
from typing import Any

import pymupdf
from openai import OpenAI

from .normalization import normalize_invoice_payload
from ..invoices.schemas import Invoice
from ..config.secrets import get_secret

SYSTEM_PROMPT = """
You extract structured data from supplier invoices.

Return exactly one JSON object with exactly these keys, and no others:
{
  "vendor_name": "string",
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "currency": "ISO 4217 code or null",
  "subtotal": number or null,
  "tax": number or null,
  "total": number,
  "document_type": "invoice" or "credit_note",
  "lines": [{"description": "string", "amount": number}]
}

Rules:
- Use only information present in the document. Never invent missing values.
- vendor_name is the supplier issuing the invoice, not the customer or bill-to party.
- Use null when due_date, subtotal, tax, or currency is absent.
- Represent dates as YYYY-MM-DD.
- Represent monetary values as decimal numbers, without currency symbols.
- Use the currency's ISO 4217 code, such as USD or GBP. Infer it from the
  document symbols or codes when clear.
- Use document_type "invoice" or "credit_note".
- Extract each line item's description and final line amount only. Do not add
  quantity or unit price keys.
- Do not include shipping or tax as a line item unless explicitly presented as
  an ordinary item.
- Do not add PO numbers, addresses, or any other fields.
""".strip()


def extract_pdf_text(pdf_path: Path) -> str:
    with pymupdf.open(pdf_path) as document:
        return "\n".join(page.get_text() for page in document)


def extract_pdf_text_from_bytes(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as document:
        return "\n".join(page.get_text() for page in document)


def configured_model() -> str:
    return os.environ["OPENROUTER_MODEL"]


def create_client(timeout: float = 90.0) -> OpenAI:
    return OpenAI(
        api_key=get_secret("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        timeout=timeout,
        max_retries=0,
    )


def parse_invoice(content: str) -> Invoice:
    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("The model returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("The model returned a JSON value that is not an object")

    return Invoice.model_validate(normalize_invoice_payload(payload))


def extract_invoice(client: OpenAI, model: str, text: str) -> Invoice:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Extract the invoice fields from this document:\n\n{text}",
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("The model returned an empty response")

    return parse_invoice(content)
