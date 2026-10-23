# Invoice Automation Platform

A practice project for building and evaluating an LLM-based invoice extraction
pipeline. It extracts a validated invoice schema from digital PDFs and can run
the extractor over the bundled
[invoice extraction benchmark](invoice-extraction-benchmark/README.md).

## Setup

```bash
uv sync
```

Create a `.env` file with:

```text
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=...
```

## Extract one invoice

```bash
python main.py
```

The result is written to `results/clean-us-clean-simple.json`.

## Run the API

```bash
uv run uvicorn invoice_automation_platform.api:app --reload
```

Or use the installed entry point:

```bash
uv run invoice-api
```

Interactive API docs are available at `http://127.0.0.1:8000/docs`.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/v1/invoices/extract` | Upload a PDF and extract an invoice |

Upload a PDF from PowerShell:

```powershell
curl.exe -F "file=@invoice.pdf;type=application/pdf" http://127.0.0.1:8000/v1/invoices/extract
```

The API accepts PDFs up to 10 MB and requires a text layer. Scanned PDFs
currently return `422` until image support is added.

## Run a benchmark batch

The batch runner selects PDF documents from the benchmark manifest and writes
predictions in the benchmark's expected format. Use `--limit` for a small,
cheap first run.

```bash
python -m invoice_automation_platform.runner --category clean --limit 5
```

Other selectors:

```bash
python -m invoice_automation_platform.runner --doc-id clean-us-clean-simple
python -m invoice_automation_platform.runner --category clean --out results/clean.json
```

Image-only documents (photos and scans) are skipped for now.

For long runs, process documents concurrently and resume after an interruption:

```bash
python -m invoice_automation_platform.runner --workers 3 --retries 2 --timeout 90 --resume
```

Completed documents are written to the predictions file as they finish, so
`--resume` skips them on the next run.

## Score the predictions

From the benchmark directory:

```bash
cd invoice-extraction-benchmark
python -m scorer.evaluate ../results/predictions.json \
  --markdown ../results/scores.md \
  --out ../results/scores.json \
  --allow-missing
```

Use `--allow-missing` for partial runs such as `--limit` batches.

## Results

The first PDF-only baseline (113 of 181 benchmark documents) is in
[benchmark-results/2026-10-23-baseline-pdf/README.md](benchmark-results/2026-10-23-baseline-pdf/README.md).

## Tests

```bash
python -m pytest
```
