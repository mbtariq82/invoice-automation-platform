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

## Tests

```bash
python -m pytest
```
