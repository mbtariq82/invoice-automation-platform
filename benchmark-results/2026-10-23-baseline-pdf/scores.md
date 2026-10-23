# invoice-automation-platform 0.1.0 (2026-10-23)

**Partial run: 113 of 181 documents scored.**

| Measure | Result |
|---|---|
| Documents with every key header field right | 88.5% (100 of 113) |
| Key header fields right | 97.6% (943 of 966) |
| Line items, mean F1 | 0.986 (111 documents; all lines right on 108) |
| Invoices whose figures do not add up, flagged | 0 of 5 |
| Files holding several invoices, flagged | 0 of 2 |
| Consistent documents flagged (false alarms) | 0 of 104 |

## Fields

| Field | Right | Scored | % |
|---|---|---|---|
| vendor_name | 113 | 113 | 100 |
| invoice_number | 110 | 111 | 99.1 |
| invoice_date | 111 | 111 | 100 |
| due_date | 74 | 74 | 100 |
| currency | 105 | 111 | 94.6 |
| subtotal | 103 | 111 | 92.8 |
| tax | 110 | 111 | 99.1 |
| total | 106 | 111 | 95.5 |
| document_type | 111 | 113 | 98.2 |
| line_items | 108 | 111 | 97.3 |
| flag | 104 | 111 | 93.7 |
| references | 0 | 16 | 0 |

## By category

| Category | Documents | Fully correct | % |
|---|---|---|---|
| clean | 31 | 31 | 100 |
| currency | 19 | 14 | 73.7 |
| tax | 14 | 11 | 78.6 |
| credit | 10 | 9 | 90 |
| multipage | 10 | 9 | 90 |
| freight | 16 | 15 | 93.8 |
| hard | 13 | 11 | 84.6 |

## By difficulty

| Difficulty | Documents | Fully correct | % |
|---|---|---|---|
| easy | 42 | 42 | 100 |
| medium | 26 | 22 | 84.6 |
| hard | 45 | 36 | 80 |

## By photo/scan severity

| Photo/scan severity | Documents | Fully correct | % |
|---|---|---|---|
