import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

from .extraction import (
    configured_model,
    create_client,
    extract_invoice,
    extract_pdf_text,
)
from .predictions import invoice_to_prediction

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = PROJECT_ROOT / "invoice-extraction-benchmark" / "corpus" / "v1"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "predictions.json"
DEFAULT_SYSTEM = "invoice-automation-platform 0.1.0"


def load_manifest(corpus_dir: Path) -> list[dict[str, Any]]:
    manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    return manifest["documents"]


def select_documents(
    documents: Iterable[dict[str, Any]],
    *,
    category: str | None = None,
    doc_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    selected = [
        document
        for document in documents
        if document.get("render") == "pdf"
        and (category is None or document["category"] == category)
        and (doc_id is None or document["doc_id"] == doc_id)
    ]
    return selected[:limit] if limit is not None else selected


def run_batch(
    *,
    corpus_dir: Path,
    output_path: Path,
    system: str,
    category: str | None = None,
    doc_id: str | None = None,
    limit: int | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    documents = select_documents(
        load_manifest(corpus_dir),
        category=category,
        doc_id=doc_id,
        limit=limit,
    )
    if not documents:
        raise ValueError("No matching PDF documents found")

    model = configured_model()
    client = create_client()
    predictions: dict[str, Any] = {}
    failures: list[dict[str, str]] = []

    for index, document in enumerate(documents, start=1):
        current = f"[{index}/{len(documents)}] {document['doc_id']}"
        try:
            text = extract_pdf_text(corpus_dir / document["file"])
            invoice = extract_invoice(client, model, text)
        except Exception as exc:
            failures.append({"doc_id": document["doc_id"], "error": str(exc)})
            print(f"{current}: failed ({exc})", file=sys.stderr)
            continue

        predictions[document["doc_id"]] = invoice_to_prediction(invoice)
        print(f"{current}: ok")

    payload = {
        "system": system,
        "run_date": date.today().isoformat(),
        "notes": (
            f"OpenRouter model {model}; extracted {len(predictions)} of "
            f"{len(documents)} selected PDF documents."
        ),
        "documents": predictions,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return output_path, failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run invoice extraction over the PDF benchmark corpus."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--system", default=DEFAULT_SYSTEM)
    parser.add_argument("--category")
    parser.add_argument("--doc-id")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    output_path, failures = run_batch(
        corpus_dir=args.corpus,
        output_path=args.out,
        system=args.system,
        category=args.category,
        doc_id=args.doc_id,
        limit=args.limit,
    )

    print(f"Saved predictions to: {output_path}")
    if failures:
        print(f"{len(failures)} documents failed; see the run log.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
