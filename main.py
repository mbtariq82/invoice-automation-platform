import json
from pathlib import Path

from invoice_automation_platform.extraction import (
    configured_model,
    create_client,
    extract_invoice,
    extract_pdf_text,
)

PROJECT_ROOT = Path(__file__).resolve().parent

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


def main() -> None:
    text = extract_pdf_text(PDF_PATH)
    invoice = extract_invoice(create_client(), configured_model(), text)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_PATH.write_text(
        json.dumps(invoice.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    print(f"Saved prediction to: {OUTPUT_PATH}")
    print(invoice.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
