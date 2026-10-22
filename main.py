
import json
import os
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from openai import OpenAI

from schemas import Invoice


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

PDF_PATH = (
    PROJECT_ROOT
    / "invoice-extraction-benchmark"
    / "corpus"
    / "v1"
    / "documents"
    / "clean-us-clean-simple.pdf"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "results"
    / "clean-us-clean-simple.json"
)


def extract_pdf_text(pdf_path: Path) -> str:
    with pymupdf.open(pdf_path) as document:
        return "\n".join(page.get_text() for page in document)


def extract_invoice(text: str) -> Invoice:
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = os.environ["OPENROUTER_MODEL"]

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": """
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
""".strip(),
            },
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


def main() -> None:
    text = extract_pdf_text(PDF_PATH)
    invoice = extract_invoice(text)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_PATH.write_text(
        json.dumps(invoice.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    print(f"Saved prediction to: {OUTPUT_PATH}")
    print(invoice.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
