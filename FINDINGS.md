# Data Quality Findings — `data/input.csv`

The 31-row source file contains a mix of clean rows and deliberately messy rows.
Below is what we observed and how each is handled.

## Summary
- **31** rows → `stage_orders` (all cleaned, typed, no constraints)
- **21** rows → `clean_orders`
- **10** rows → `rejected_orders` (7 missing-required + 2 business-rule + 1 duplicate)

## Issues handled by cleaners (row stays valid)

### Whitespace / casing / missing tokens
- Stray leading/trailing whitespace and double spaces in names, addresses,
  and notes.
- Missing-value tokens like `""`, `N/A`, `NA`, `NULL`, `NONE`, `NAN` —
  normalized to `NULL`.

### Emails
- Mixed casing → lowercased.
- Invalid forms (multiple `@`, embedded whitespace, missing dot in domain,
  domain starting/ending with `.`) → `NULL`.

### Phones
- Many surface formats: `(555) 123-4567`, `555.123.4567`, `+1 555 123 4567`,
  with extensions written `ext`, `ext.`, `extension`, `x`, `ex`.
- Cleaner strips the extension, keeps only digits, requires length 7–15.
- Free-text junk like `call me` → `NULL`.

### Dates
- Multiple formats: ISO (`2025-07-19`), ISO+`Z`, US `MM/DD/YYYY`,
  EU `DD-MM-YYYY`, slash+time. All parsed.
- Impossible dates like `2025-02-30` → `NaT`.

### Amounts
- Currency symbols / codes / spaces stripped: `$1,299.99`, `USD 1299.99`,
  `1 299,99` all parse.
- US/EU separator handled by a position heuristic (last separator wins as
  decimal mark). `1,299.99` → `1299.99`; `1.299,99` → `1299.99`.
- Lone comma with 1–2 trailing digits treated as decimal: `29,99` → `29.99`.
- Stored as `Decimal` end-to-end — never `float`.

### Quantities
- Whitespace, missing tokens. Negative or non-integer values become `NaN`
  via `pd.to_numeric(errors="coerce")` and then fail the required-field
  check downstream.

### Country / currency codes
- Uppercased; only ISO-shape codes accepted (`^[A-Z]{2}$` / `^[A-Z]{3}$`).
  Anything else → `NULL`.

### Postal codes
- Trimmed and uppercased (e.g. UK postcodes). No format enforcement —
  varies too much by country to be worth more.

## Issues that cause rejection

A row is rejected for any of:

1. **Missing required field** — `order_id`, `customer_id`, `customer_name`,
   `item_sku`, `item_name`, `order_date`, `quantity`, or `unit_price` is
   `NULL` after cleaning.
2. **Business-rule violation** — `ship_date < order_date`,
   `quantity <= 0`, or `unit_price < 0`.
3. **Duplicate** — second (or later) occurrence of `(order_id, item_sku)`.

Rejected rows from `data/input.csv`:

| row | order_id | item_sku       | reason                          |
|----:|---------:|----------------|---------------------------------|
|   5 |     1006 |                | missing order_date              |
|   7 |     1008 |                | missing quantity                |
|   8 |     1007 | `SKU-ETA-07`   | ship_date before order_date     |
|  10 |     1009 | `SKU-IOTA-09`  | quantity <= 0                   |
|  11 |     1012 |                | missing customer_name           |
|  19 |     1020 |                | missing quantity                |
|  20 |     1021 |                | missing unit_price              |
|  25 |     1001 | `SKU-ALPHA-01` | duplicate (order_id, item_sku)  |
|  26 |   `NULL` |                | missing order_id                |
|  29 |     1029 |                | missing unit_price              |

The duplicate at row 25 is a re-occurrence of order `(1001, SKU-ALPHA-01)`
from row 1 — the first occurrence is kept in `clean_orders`, the second is
routed here. Without this guard the batch insert would fail on the
`UNIQUE(order_id, item_sku)` constraint with MySQL error 1062.

Cross-row duplicates on `(order_id, item_sku)` are detected before insert,
so a single bad row never blocks an entire load.

The original raw text is preserved in `rejected_orders` so the row can be
re-processed manually or after a rules change.