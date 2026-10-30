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
VERTEX_AI_MODEL=gemini-2.5-flash
GOOGLE_CLOUD_LOCATION=global
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

## Google Cloud Secret Manager

The application can load its database URL and model API key directly from
Secret Manager. Set numbered secret-version references instead of plaintext
credentials:

```text
DATABASE_URL_SECRET_VERSION=projects/your-project/secrets/invoice-dev-database-url/versions/1
VERTEX_AI_MODEL=gemini-2.5-flash
GOOGLE_CLOUD_LOCATION=global
```

Terraform configures these references for the Cloud Run API and supplies only
the database reference to the migration job. Google authentication uses the
attached runtime service account, which has access to the two specific secrets.
Terraform also reads provisioning credentials from Secret Manager: bootstrap
creates empty source secrets, you populate them once in the Google Cloud
console, and subsequent plans use numbered versions without password prompts.
See the [infrastructure setup guide](infra/README.md) for those steps.
For local cloud access, run `gcloud auth application-default login` using an
account with Secret Manager Secret Accessor permission on those secrets.

Each secret is fetched on first use, checked for payload integrity and cached
in memory for the process lifetime. Use a numbered version, rather than
`latest`; deploy a new version reference to rotate credentials. A configured
reference takes precedence over `.env` values and failures never fall back to
local credentials. The resolver does not log secret values or write them to files.

Without the `*_SECRET_VERSION` settings, the existing `.env` configuration
continues to work without Google credentials. Health checks do not fetch secrets.
The test suite uses mocked Secret Manager responses and makes no cloud calls.

The database URL created by Terraform uses Cloud Run's `/cloudsql` socket. For
local development, keep `DATABASE_URL` pointing at your local Postgres database
or a local Cloud SQL Auth Proxy, and set only the API key's secret reference
unless you also have the required database socket available.

## Extract one invoice

```bash
python main.py
```

The result is written to `results/clean-us-clean-simple.json`.

## Run the API

```bash
uv run uvicorn invoice_automation_platform.api:app --reload --loop invoice_automation_platform.api.event_loop:loop_factory
```

The API uses SQLAlchemy's async engine and sessions with psycopg. The custom
loop factory selects a Windows-compatible event loop for local development;
`uv run invoice-api` uses it automatically. Alembic continues using psycopg's
synchronous engine with the same database URL. API shutdown releases pooled
database connections and closes the Vertex AI client.

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

After changing `src/invoice_automation_platform/db/models.py`, generate a new
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
python -m invoice_automation_platform.evaluation.runner --category clean --limit 5
```

Other selectors:

```bash
python -m invoice_automation_platform.evaluation.runner --doc-id clean-us-clean-simple
python -m invoice_automation_platform.evaluation.runner --category clean --out results/clean.json
```

Image-only documents (photos and scans) are skipped for now.

For long runs, process documents concurrently and resume after an interruption:

```bash
python -m invoice_automation_platform.evaluation.runner --workers 3 --retries 2 --timeout 90 --resume
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

The [React frontend](docs/frontend.md) provides Google sign-in, PDF upload,
invoice history and detail review. It runs on Cloud Run with a dedicated proxy
identity so the FastAPI service remains private.

[CI/CD setup and release flow](docs/ci-cd.md) describes GitHub Actions CI, Google
Cloud Build container builds, keyless GCP authentication, and Google Cloud
Deploy migrations, progressive canary verification and rollback.

[Terraform setup and deployment instructions](infra/README.md) define a
development environment with Cloud Run, Cloud SQL for PostgreSQL, Secret
Manager, Artifact Registry, and a private Cloud Storage bucket for PDF invoices.
The setup uses a separate bucket for Terraform state and supports provisioning
the infrastructure before deploying an application image.
