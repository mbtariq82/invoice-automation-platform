import os
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from openai import OpenAI

from .schemas import Invoice

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SYSTEM_PROMPT = """
You extract structured data from supplier invoices.

Use only information present in the document.
Never invent missing values.
Return null for missing dates and subtotal or tax values.
Represent dates as YYYY-MM-DD.
Represent monetary values as decimal numbers, without currency symbols.
Use the currency's ISO 4217 code, such as USD or GBP.
Use document_type "invoice" or "credit_note".
Extract each line item's description and final line amount.
Do not include shipping or tax as a line item unless explicitly
presented as an ordinary item.
Return a JSON object matching the requested fields.
""".strip()

load_dotenv(PROJECT_ROOT / ".env")


def extract_pdf_text(pdf_path: Path) -> str:
    with pymupdf.open(pdf_path) as document:
        return "\n".join(page.get_text() for page in document)


def configured_model() -> str:
    return os.environ["OPENROUTER_MODEL"]


def create_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )


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

    return Invoice.model_validate_json(content)
