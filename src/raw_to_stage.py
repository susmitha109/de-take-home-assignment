"""
Step 2 - Raw to Stage.

Reads raw_orders for one input_file_name, applies per-column cleaners,
and writes the typed result to stage_orders. No validation here -
every cleaned row is written, good or bad.

Idempotent: skips if the file is already in stage_orders.

Usage:
    python -m src.raw_to_stage --config config.json --input /full/path/to/input.csv
"""

import json
import os
import sys
from argparse import ArgumentParser
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


CSV_COLUMNS = (
    "order_id", "customer_id", "customer_name", "email", "phone",
    "country", "state", "city", "address", "postal_code",
    "order_date", "ship_date", "ship_mode",
    "item_sku", "item_name", "quantity", "unit_price", "currency",
    "discount_code", "order_notes",
)

MISSING = {"", "N/A", "NA", "NULL", "NONE", "NAN"}

DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
)


# ---------- per-column cleaners (Series -> Series) ----------

def clean_text(s):
    out = s.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    out[out.str.upper().isin(MISSING)] = pd.NA
    return out


def clean_email(s):
    out = clean_text(s).str.lower()
    domain = out.str.split("@").str[-1]
    valid = (
        out.str.count("@").eq(1)
        & ~out.str.contains(r"\s", na=False)
        & domain.str.contains(".", regex=False, na=False)
        & ~domain.str.startswith(".", na=False)
        & ~domain.str.endswith(".", na=False)
    )
    return out.where(valid)


def clean_phone(s):
    txt = clean_text(s).str.lower()
    main = txt.str.split(r"\s*(?:extension|ext|ex|x)\s*", regex=True).str[0]
    digits = main.str.replace(r"\D", "", regex=True)
    return digits.where(digits.str.len().between(7, 15))


def _parse_date(s):
    if pd.isna(s):
        return pd.NaT
    try:
        return pd.Timestamp(datetime.fromisoformat(s.replace("Z", "+00:00"))).tz_localize(None)
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return pd.Timestamp(datetime.strptime(s, fmt))
        except ValueError:
            pass
    return pd.NaT


def clean_date(s):
    return pd.to_datetime(clean_text(s).map(_parse_date)).dt.normalize()


def _parse_amount(s):
    # Last separator wins as decimal mark; lone comma with 1-2 trailing digits is decimal.
    if pd.isna(s) or not s:
        return None
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # comma is last -> EU
        else:
            s = s.replace(",", "")                     # dot is last -> US
    elif "," in s:
        last = s.rsplit(",", 1)[-1]
        if 1 <= len(last) <= 2 and last.isdigit():
            s = s.replace(",", ".")                    # decimal
        else:
            s = s.replace(",", "")                     # thousands
    try:
        return Decimal(s)
    except InvalidOperation:
        return None

def clean_amount(s):
    s = clean_text(s).str.replace(r"[^\d.,\-]", "", regex=True)
    return s.map(_parse_amount).astype("object")


def clean_quantity(s):
    return pd.to_numeric(clean_text(s), errors="coerce").astype("Int64")


def clean_country(s):
    out = clean_text(s).str.upper()
    return out.where(out.str.match(r"^[A-Z]{2}$", na=False))


def clean_currency(s):
    out = clean_text(s).str.upper()
    return out.where(out.str.match(r"^[A-Z]{3}$", na=False))


def clean_postal_code(s):
    return clean_text(s).str.upper()


def clean_dataframe(raw):
    df = raw.copy()
    for c in ["order_id", "customer_id", "customer_name", "state", "city",
              "address", "ship_mode", "item_sku", "item_name",
              "discount_code", "order_notes"]:
        df[c] = clean_text(df[c])

    df["email"]       = clean_email(df["email"])
    df["phone"]       = clean_phone(df["phone"])
    df["country"]     = clean_country(df["country"])
    df["postal_code"] = clean_postal_code(df["postal_code"])
    df["currency"]    = clean_currency(df["currency"])
    df["order_date"]  = clean_date(df["order_date"])
    df["ship_date"]   = clean_date(df["ship_date"])
    df["quantity"]    = clean_quantity(df["quantity"])
    df["unit_price"]  = clean_amount(df["unit_price"])
    return df


# ---------- pipeline step ----------

def transform_raw_to_stage(config_path: str, input_path: str) -> int:
    cfg = json.loads(Path(config_path).read_text())
    engine = create_engine(
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    )
    input_file_name = os.path.basename(input_path)

    existing = pd.read_sql(
        text("SELECT 1 FROM stage_orders WHERE input_file_name = :f LIMIT 1"),
        engine, params={"f": input_file_name},
    )
    if not existing.empty:
        print(f"[SKIP] '{input_file_name}' already in stage_orders.")
        return 0

    raw = pd.read_sql(
        text("SELECT source_row_id, " + ", ".join(CSV_COLUMNS)
             + " FROM raw_orders WHERE input_file_name = :f"),
        engine, params={"f": input_file_name},
    )

    cleaned = clean_dataframe(raw[list(CSV_COLUMNS)])
    cleaned["source_row_id"] = raw["source_row_id"].values
    cleaned["input_file_name"] = input_file_name
    cleaned.to_sql("stage_orders", engine, if_exists="append", index=False)

    print(f"[OK] {input_file_name}: {len(cleaned)} rows -> stage_orders.")
    return len(cleaned)


def main() -> int:
    parser = ArgumentParser(description="Clean raw_orders -> stage_orders.")
    parser.add_argument("--config", required=True, help="Path to MySQL config JSON file")
    parser.add_argument("--input",  required=True, help="Path to the original CSV (basename used as lookup key)")
    args = parser.parse_args()
    transform_raw_to_stage(args.config, args.input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
