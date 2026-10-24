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
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/invoice_automation
TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/invoice_automation_test
```

Create the two Postgres databases (names can differ, just match the URLs
above), then apply migrations:

```bash
uv run alembic upgrade head
```

`TEST_DATABASE_URL` is a separate database used only by the test suite; its
tables are created and dropped automatically per test session.

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
| GET | `/v1/invoices` | List previously extracted invoices (`limit`, `offset`) |
| GET | `/v1/invoices/{id}` | Fetch one extracted invoice |

Upload a PDF from PowerShell:

```powershell
curl.exe -F "file=@invoice.pdf;type=application/pdf" http://127.0.0.1:8000/v1/invoices/extract
```

The API accepts PDFs up to 10 MB and requires a text layer. Scanned PDFs
currently return `422` until image support is added.

Every extraction is persisted in Postgres, keyed by the SHA-256 of the
uploaded bytes. Uploading the same PDF again skips the model call and returns
the stored result with `"cached": true`.

Invoice responses include a `totals_check`, computed from the stored amounts:

```json
{
  "status": "mismatch",
  "subtotal_plus_tax": "110.00",
  "difference": "15.00",
  "reason": "Total differs from subtotal plus tax by more than 0.01; shipping, discounts, or other adjustments may explain the difference."
}
```

`matched` means subtotal plus tax agrees with total within 0.01 (inclusive).
`mismatch` reports a larger difference; `difference` is total minus
`subtotal_plus_tax`. Missing subtotal or tax returns `not_checked` with null
calculated amounts. An explicit zero tax is checked. Calculations use `Decimal`
and retain credit-note signs. The fixed 0.01 tolerance currently targets
two-decimal monetary amounts.

This is a header arithmetic diagnostic, not approval or proof of invoice
accuracy. Shipping, discounts and other adjustments are not yet captured in
the schema and can explain a mismatch. Matching headers can still hide line
errors or an incorrect tax rate. The check preserves extracted values and
does not set the benchmark's `flagged` field. It is recomputed for uploads,
cached results, lists and individual records; no database migration is needed.

After changing `src/invoice_automation_platform/models.py`, generate a new
migration and apply it:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

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

## GCP infrastructure

[Terraform setup and deployment instructions](infra/README.md) define a
development environment with Cloud Run, Cloud SQL for PostgreSQL, Secret
Manager, Artifact Registry, and a private Cloud Storage bucket for PDF invoices.
The setup uses a separate bucket for Terraform state and supports provisioning
the infrastructure before deploying an application image.
