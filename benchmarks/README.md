# Compare invoice AI models

The comparison uses the current text-based PDF pipeline without touching the API,
database or upload cache. It is separate from the original single-model runner.

## Candidates

| Name | Model through OpenRouter | Tasks |
|---|---|---|
| openai | `openai/gpt-5.4-mini` | Extraction and decisions |
| anthropic | `anthropic/claude-sonnet-4.6` | Extraction and decisions |
| jev | `typesafe/jev-1.14` (TypeSafe release `jev-1.14.0`) | Decisions |
| google | `google/gemini-3.1-pro-preview` | Extraction and decisions |

Gemini is the fourth candidate, providing a third independent generative model
family. These are explicit model versions, not claims that they are the newest
models from each company. Gemini is a preview. Actual served model/provider IDs
are retained in every response and collected in each score file.

**Jev is not a generative invoice extractor.** It returns decisions from defined
answer spaces. Its extraction result is not applicable, rather than zero or a
fabricated prediction. Jev Router is a different product and is not used.

There are two independent tasks:

1. **Extraction:** the three chat models receive the same extracted text, existing
   production prompt, schema, normalisation and validation. All three use the same
   strict JSON-schema response format (the older production path uses JSON-object
   mode). This wire-format improvement means results are not an exact rerun of the
   old baseline. The bundled official
   scorer compares headers and lines with the selected manifest's expected values.
   Statements cannot be represented by the current production schema; review flags
   and references are hardcoded by its adapter. These remain platform limitations.
2. **Decisions:** all four candidates independently receive the same text and task
   definitions. They classify `invoice` / `credit_note` / `other`, and identify
   documents whose figures conflict or which contain multiple invoices. Chat
   models return strict JSON; Jev answers Choice and Noul questions through
   `POST /api/alpha/decisions`. No extraction answer is fed into this task.

The review task uses the corpus's labels, which are narrower than every possible
reason for manual review. Shipping/discounts are not automatically inconsistencies.
Jev's Noul probability is thresholded at 0.5 by default; fix or tune that threshold
on development data, not the final evaluation set.

## Run

Install/update dependencies with `uv sync`. Use the existing `OPENROUTER_API_KEY`
or its numbered Secret Manager reference. No separate TypeSafe key is needed.

Validate the full plan without credentials, API requests or output files:

```powershell
uv run invoice-benchmark --dry-run
```

Start with a small cross-category smoke run (this makes billed API requests):

```powershell
uv run invoice-benchmark --limit 14 --out results/comparison-smoke
```

Run all 113 digital PDFs with three independent repeats:

```powershell
uv run invoice-benchmark --repeats 3 --workers 3 --out results/comparison-full
```

All candidates together have seven tasks per document per repeat: three
extraction calls and four decision calls. A full three-repeat run therefore
starts with **2,373 requests**, with a maximum of **7,119 attempts** at the default
two retries. The dry run prints the maximum request count for your selection.
An initial 14-document run has 98 requests before retries. There is no monetary
budget cap; use a small selection and an account/key spending limit when needed.

Resume an interrupted run with the exact original options:

```powershell
uv run invoice-benchmark --repeats 3 --workers 3 --out results/comparison-full --resume
```

Completed documents, including exhausted failures, are not requested again.
Completed document checkpoints are atomic. An interruption while a request is
in flight can leave an unrecorded charge; resume may repeat that document. Check
gateway billing for exact reconciliation after an interrupted run.

Select candidates or tasks, or change the configuration explicitly:

```powershell
uv run invoice-benchmark --candidate jev --task decisions --limit 14 --out results/jev-smoke
uv run invoice-benchmark --candidate openai --candidate anthropic --task extraction --out results/extraction
uv run invoice-benchmark --config benchmarks/models.json --dry-run
```

`--limit` draws round-robin across available PDF categories; it is a development
sample, not a representative production distribution. `--category` narrows the
selection. The 68 photo/scan/handwritten image documents are outside this test.

## Controls and output

- Each model/task/repeat has its own directory, predictions and scores.
- `run.json` records prompts, settings, runtime versions, code revision, source
  hashes, document/text hashes, selection and a resume fingerprint. Changes to
  these reject a resume. Use a new directory for a new experiment.
- `documents/<id>.json` retains responses, model/provider identity, usage, attempt
  times and safe error categories. These artifacts contain invoice/model data;
  they are saved under the existing ignored `results` directory by default.
- `comparison.md` is the readable scorecard. `comparison.json` also contains
  per-document results and paired wins/losses for matching tasks and repeats.
- Extraction scores include headers, line-item F1, and category/difficulty results.
  Decision scores include classification accuracy, review precision/recall and
  category breakdowns. Failed requests remain in the fixed selected denominator.
- Costs use gateway-reported `usage.cost`, including successful-but-invalid
  responses and retries. Missing cost information is unknown, never zero. The
  known sum is a lower bound when cost reporting is incomplete. Cost per invoice
  and per fully correct invoice are null in that case.
- Median/p95 document latency includes HTTP attempts, parsing and retry backoff,
  excluding PDF preparation and queue time. Default workers=1 is best for a simple
  latency comparison; concurrent runs also reflect rate limits and contention.
- 408, 429 and server errors, transport errors and invalid outputs are retried.
  Other HTTP errors (including auth errors) are not retried. Failures cause a
  nonzero command exit after reports are written.
- The shared chat output cap defaults to 8,192 tokens. Truncated outputs are
  failures. Model-native reasoning differs: GPT uses none, Claude disables it,
  Gemini uses low. GPT does not accept temperature here; the others use zero.
  These explicit settings are recorded rather than claiming identical compute.
- Chat requests disable provider fallback and require support for the supplied
  parameters. Set a candidate's optional `provider` to an OpenRouter provider slug
  to restrict its host. Without that setting, report this as a model comparison
  through OpenRouter, not a direct API/provider benchmark.

Do not tune against all public answers and then describe the same set as held out.
Use this synthetic public corpus for development/regression and validate finalists
on independently labelled real invoices, held out by supplier/layout. Repeats
measure stability; they do not increase the number of independent invoices.

## Verified API references

Checked 25 October 2026:

- [OpenAI GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Anthropic Sonnet 4.6](https://www.anthropic.com/news/claude-sonnet-4-6)
- [Google Gemini 3.1 Pro preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview)
- [TypeSafe model releases](https://docs.typesafe.ai/models)
- [OpenRouter Jev support and endpoints](https://openrouter.ai/docs/guides/community/jev)
- [Decisions request/response examples](https://openrouter.ai/docs/guides/community/jev-tutorial)
- [Usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)

Network-free tests use mocked HTTP responses. Real account access, serving
availability and billed performance must be established by an actual live run.
