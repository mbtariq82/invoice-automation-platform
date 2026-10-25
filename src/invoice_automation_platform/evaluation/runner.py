import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..extraction import (
    configured_model,
    create_client,
    extract_invoice,
    extract_pdf_text,
)
from .predictions import invoice_to_prediction

PROJECT_ROOT = Path(__file__).resolve().parents[3]
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


def _extract_one(
    document: dict[str, Any],
    corpus_dir: Path,
    client: Any,
    model: str,
    retries: int,
) -> tuple[str, dict[str, Any] | None, str | None]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            text = extract_pdf_text(corpus_dir / document["file"])
            invoice = extract_invoice(client, model, text)
            return document["doc_id"], invoice_to_prediction(invoice), None
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
    return document["doc_id"], None, str(last_error)


def _write_payload(
    output_path: Path,
    system: str,
    model: str,
    predictions: dict[str, Any],
    documents_count: int,
    workers: int,
    failures: list[dict[str, str]],
) -> None:
    payload = {
        "system": system,
        "run_date": date.today().isoformat(),
        "notes": (
            f"OpenRouter model {model}; extracted {len(predictions)} of "
            f"{documents_count} selected PDF documents with {workers} workers; "
            f"{len(failures)} failed."
        ),
        "documents": dict(sorted(predictions.items())),
        "failures": sorted(failures, key=lambda item: item["doc_id"]),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_batch(
    *,
    corpus_dir: Path,
    output_path: Path,
    system: str,
    category: str | None = None,
    doc_id: str | None = None,
    limit: int | None = None,
    workers: int = 1,
    retries: int = 2,
    resume: bool = False,
    timeout: float = 90.0,
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
    client = create_client(timeout=timeout)
    predictions: dict[str, Any] = {}
    failures: list[dict[str, str]] = []

    if resume and output_path.exists():
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        selected_ids = {document["doc_id"] for document in documents}
        predictions = {
            doc_id: prediction
            for doc_id, prediction in (raw.get("documents") or {}).items()
            if doc_id in selected_ids
        }
        failures = [
            failure
            for failure in (raw.get("failures") or [])
            if failure["doc_id"] in selected_ids
        ]

    pending = [
        document for document in documents if document["doc_id"] not in predictions
    ]
    if not pending:
        _write_payload(
            output_path,
            system,
            model,
            predictions,
            len(documents),
            workers,
            failures,
        )
        return output_path, failures

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_extract_one, document, corpus_dir, client, model, retries)
            for document in pending
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            doc_id, prediction, error = future.result()
            current = f"[{index}/{len(pending)}] {doc_id}"
            failures[:] = [item for item in failures if item["doc_id"] != doc_id]
            if error is not None:
                failures.append({"doc_id": doc_id, "error": error})
                print(f"{current}: failed ({error})", file=sys.stderr)
            else:
                predictions[doc_id] = prediction
                print(f"{current}: ok")

            _write_payload(
                output_path,
                system,
                model,
                predictions,
                len(documents),
                workers,
                failures,
            )

    _write_payload(
        output_path,
        system,
        model,
        predictions,
        len(documents),
        workers,
        failures,
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
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.retries < 0:
        parser.error("--retries must be zero or more")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    output_path, failures = run_batch(
        corpus_dir=args.corpus,
        output_path=args.out,
        system=args.system,
        category=args.category,
        doc_id=args.doc_id,
        limit=args.limit,
        workers=args.workers,
        retries=args.retries,
        resume=args.resume,
        timeout=args.timeout,
    )

    print(f"Saved predictions to: {output_path}")
    if failures:
        print(f"{len(failures)} documents failed; see the run log.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
