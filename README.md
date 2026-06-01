# Manulife Data Engineer — Take-Home

Ingests a customer-orders CSV into MySQL with full quality handling.
Bad rows are quarantined with a reason; clean rows land in a typed table; the
original CSV row is always preserved for audit and replay.

---

## Stack
- Python 3.11+
- pandas (parsing / transforms)
- pytest (unit tests)
- MySQL (target storage)

## Project layout
```
manulife-de-takehome/
├── data/input.csv                # source CSV (31 rows, with planted edge cases)
├── sql/schema.sql                # DDL: raw / stage / clean / rejected tables
├── src/
│   ├── csv_to_raw.py             # CSV          → raw_orders                 (bronze)
│   ├── raw_to_stage.py           # raw_orders   → stage_orders               (silver)
│   ├── stage_to_published.py     # stage_orders → clean_orders + rejected_orders (gold)
│   └── pipeline.py               # convenience wrapper: runs all three in order
├── tests/test_cleaners.py        # one scenario test per cleaner
├── config.example.json           # MySQL connection config template
├── requirements.txt
├── FINDINGS.md                   # data-quality observations on the test file
└── README.md
```

## Architecture (medallion)
```
   CSV file
      │  csv_to_raw            (lossless TEXT load)
      ▼
   raw_orders                  ── raw ──
      │  raw_to_stage          (per-column cleaners; typed; no validation)
      ▼
   stage_orders                ── silver ──
      │  stage_to_published    (split on required fields)
      ├──────────────► clean_orders        ── gold (good) ──
      └──────────────► rejected_orders     ── gold (bad)  ──
```

Every downstream table carries a `source_row_id` lineage column pointing back
to `raw_orders.source_row_id`, so any row in any layer can be traced to the
exact CSV row it came from.

---

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json   # then edit with your MySQL creds
```

`config.json`:
```json
{
  "host": "localhost",
  "port": 3306,
  "user": "root",
  "password": "...",
  "database": "manulife_takehome"
}
```

## Run
```bash
# 1. Create database + tables
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS manulife_takehome;"
mysql -u root -p manulife_takehome < sql/schema.sql

# 2a. Run the full pipeline end-to-end
python -m src.pipeline \
    --config config.json \
    --input "$(pwd)/data/input.csv"

# 2b. ...or run each stage individually (this is what an orchestrator does):
python -m src.csv_to_raw         --config config.json --input "$(pwd)/data/input.csv"
python -m src.raw_to_stage       --config config.json --input "$(pwd)/data/input.csv"
python -m src.stage_to_published --config config.json --input "$(pwd)/data/input.csv"

# 3. Tests
pytest -v
```

Each stage is **idempotent** — re-running it on the same `input_file_name` is
a no-op (skip with a log line). Each stage checks its own output table for
prior runs, so they can be re-run independently.

---

## Approach

### 1. Bronze — `csv_to_raw.py` → `raw_orders`
- Reads the CSV with `dtype=str, keep_default_na=False, na_filter=False`. Nothing
  is silently coerced (no NaN on `""`, no float on `89,99`, no NaT on weird
  dates). What lands in MySQL is byte-for-byte the source row.
- All columns are `TEXT`. Two audit columns: `source_row_id` (PK,
  auto-increment), `input_file_name`, `create_ts` (server `DEFAULT CURRENT_TIMESTAMP`).
- Idempotent: skips if any row with the same `input_file_name` already exists.
- `to_sql(method="multi", chunksize=500)` for batched inserts.

### 2. Silver — `raw_to_stage.py` → `stage_orders`
Per-column cleaners — each is a `Series → Series` function.

| column          | what the cleaner does |
|-----------------|----------------------|
| free text       | trim, collapse whitespace, normalize missing tokens (`N/A`, `NULL`, `""`, …) → `NULL` |
| `email`         | lowercase, validate single `@`, no whitespace, dot in domain |
| `phone`         | strip extension (`ext`/`extension`/`x`), keep digits only, require length 7–15 |
| `order_date` / `ship_date` | parse ISO, ISO+`Z`, US `MM/DD/YYYY`, EU `DD-MM-YYYY`, slash+time; invalid → `NaT` |
| `unit_price`    | `Decimal` (never float); position-based US/EU separator heuristic |
| `quantity`      | `pd.to_numeric` → nullable `Int64` |
| `country`       | uppercase; only ISO-2 (`^[A-Z]{2}$`) accepted |
| `currency`      | uppercase; only ISO-3 (`^[A-Z]{3}$`) accepted |
| `postal_code`   | trim + uppercase |

All cleaned rows (good and bad) land in `stage_orders`, typed but with **no
NOT NULL or UNIQUE constraints**. This is the pivot point: if validation
rules change later, we re-split from stage instead of re-cleaning from raw.

### 3. Gold — `stage_to_published.py` → `clean_orders` + `rejected_orders`
A row is **valid** iff all required fields are non-NULL after cleaning:

```
order_id, customer_id, customer_name, item_sku, item_name,
order_date, quantity, unit_price
```

- **Valid** rows → `clean_orders` (typed columns, `UNIQUE(order_id, item_sku)`).
- **Rejected** rows → `rejected_orders` with `rejection_reason = "missing <first_missing_col>"`.
  The lossless original text is fetched from `raw_orders` via `source_row_id`,
  so the rejected row is human-readable without re-running anything.

---

## Results on `data/input.csv` (31 rows)
| table              | rows |
|--------------------|-----:|
| `raw_orders`       | 31   |
| `stage_orders`     | 31   |
| `clean_orders`     | 24   |
| `rejected_orders`  | 7    |

See [FINDINGS.md](FINDINGS.md) for the per-row rejection reasons and the full
list of data-quality issues observed and how each is handled.

---

## Tradeoffs and limitations
- **Amount parsing is heuristic, not currency-aware.** Position of the last
  separator decides decimal vs thousands. The alternative — trusting the
  `currency` column — fails when `currency` itself is dirty. Row 31 of the
  test file pairs `29,99` with `USD`; the heuristic reads it as `29.99`
  (correct), a metadata-driven parser would read it as `2999.00`. A worked
  alternative is left as a commented block in `raw_to_stage.py` for
  comparison.
- **Config is a JSON file** (`--config config.json`), not `.env` or a
  secrets manager. Keeps creds out of shell history and is trivial to swap
  per environment; production would use env vars, AWS Secrets Manager, or
  similar.
- **No incremental / CDC support.** Each run processes one whole file
  identified by `input_file_name`. Re-runs are skipped, not merged.
