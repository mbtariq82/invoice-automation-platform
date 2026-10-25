# Baseline: PDF subset (113 of 181)

- **Run date:** 2026-10-23
- **System:** invoice-automation-platform 0.1.0
- **Model:** `openrouter/free` via OpenRouter
- **Scope:** the 113 digital PDFs with a text layer
- **Not run:** 53 JPEG and 15 PNG documents; the extractor is text-only

This is a partial benchmark run. The official scorer was invoked with
`--allow-missing`, so only the 113 PDF documents are scored.

## Headline results

| Measure | Result |
|---|---|
| Documents with every key header field right | 88.5% (100 of 113) |
| Key header fields right | 97.6% (943 of 966) |
| Line items, mean F1 | 0.986 (111 documents; all lines right on 108) |
| Inconsistent invoices flagged | 0 of 5 |
| Multi-invoice files flagged | 0 of 2 |
| Consistent documents flagged (false alarms) | 0 of 104 |

The full scorer output is in [scores.md](scores.md).

## By category

| Category | Documents | Fully correct | % |
|---|---:|---:|---:|
| clean | 31 | 31 | 100 |
| currency | 19 | 14 | 73.7 |
| tax | 14 | 11 | 78.6 |
| credit | 10 | 9 | 90 |
| multipage | 10 | 9 | 90 |
| freight | 16 | 15 | 93.8 |
| hard | 13 | 11 | 84.6 |

All easy documents were fully correct (42 of 42). The weak categories are
dual-currency invoices and VAT-inclusive tax layouts.

## Field-level gaps

| Field | Right | Scored | % |
|---|---:|---:|---:|
| currency | 105 | 111 | 94.6 |
| subtotal | 103 | 111 | 92.8 |
| total | 106 | 111 | 95.5 |
| tax | 110 | 111 | 99.1 |
| invoice_number | 110 | 111 | 99.1 |
| document_type | 111 | 113 | 98.2 |
| line_items | 108 | 111 | 97.3 |
| flag | 104 | 111 | 93.7 |
| references | 0 | 16 | 0 |

Vendor, invoice date, and due date were 100% correct. The 13 documents that
were not fully correct failed on:

- **Dual-currency invoices** (4): the extractor does not consistently pick the
  amount-payable box and its currency.
- **VAT-inclusive layouts** (3): the extracted subtotal is the printed
  tax-inclusive value instead of the net amount before VAT.
- **Statements** (2): `document_type` is `invoice`; the schema does not support
  `other`.
- **Inconsistent or multi-invoice documents** (7): the adapter hardcodes
  `flagged: false`, so none are held for review.
- **Missing invoice number** (1 credit note): the reference suffix was missed.
- **One multipage document**: currency and line items were misread.
- **One freight invoice**: subtotal and total were misread, and references
  were not extracted.

## What to fix next

1. Add arithmetic validation and set `flagged` for inconsistent invoices.
2. Support `other` documents and extract references.
3. Handle dual-currency amount-payable boxes and VAT-inclusive subtotals.
4. Add image support for the remaining 68 benchmark documents.

## Reproduce

```powershell
python -m invoice_automation_platform.evaluation.runner --workers 3 --retries 2 --timeout 90 --resume --out results\baseline-pdf.json

Push-Location invoice-extraction-benchmark
..\.venv\Scripts\python.exe -m scorer.evaluate ..\results\baseline-pdf.json --markdown ..\results\baseline-scores.md --out ..\results\baseline-scores.json --allow-missing
Pop-Location
```
