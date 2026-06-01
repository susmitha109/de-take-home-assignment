"""
Step 3 - Stage to Final.

Reads stage_orders for one input_file_name, splits into valid and rejected
based on required-field presence, and writes:
  - clean_orders     (valid rows, typed)
  - rejected_orders  (lossless raw text + rejection reason)

Idempotent: skips if the file is already in clean_orders.

Usage:
    python -m src.stage_to_published --config config.json --input /full/path/to/input.csv
"""

import json
import os
import sys
from argparse import ArgumentParser
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, create_engine, text


STAGE_COLUMNS = (
    "source_row_id",
    "order_id", "customer_id", "customer_name", "email", "phone",
    "country", "state", "city", "address", "postal_code",
    "order_date", "ship_date", "ship_mode",
    "item_sku", "item_name", "quantity", "unit_price", "currency",
    "discount_code", "order_notes",
)

REQUIRED = [
    "order_id", "customer_id", "customer_name",
    "item_sku", "item_name",
    "order_date", "quantity", "unit_price",
]

DEDUP_KEY = ["order_id", "item_sku"]


def split_records(df):
    bad_mask = df[REQUIRED].isna().any(axis=1)
    good = df[~bad_mask].copy()
    bad = df[bad_mask].copy()
    if not bad.empty:
        bad["rejection_reason"] = "missing " + df[REQUIRED].isna().idxmax(axis=1).loc[bad.index]
    return good, bad


def split_business_rules(df):
    # Cross-field / range checks. First matching rule wins per row.
    rules = [
        (
            df["ship_date"].notna() & df["order_date"].notna()
            & (df["ship_date"] < df["order_date"]),
            "ship_date before order_date",
        ),
        (
            df["quantity"].notna() & (df["quantity"] <= 0),
            "quantity <= 0",
        ),
        (
            df["unit_price"].map(lambda v: v is not None and v < 0),
            "unit_price negative",
        ),
    ]

    reason = pd.Series(pd.NA, index=df.index, dtype="object")
    for cond, msg in rules:
        reason[cond & reason.isna()] = msg

    bad_mask = reason.notna()
    good = df[~bad_mask].copy()
    bad  = df[bad_mask].copy()
    if not bad.empty:
        bad["rejection_reason"] = reason[bad_mask]
    return good, bad


def split_duplicates(df):
    # Keep first occurrence; later rows with the same (order_id, item_sku) go to rejected.
    dup_mask = df.duplicated(subset=DEDUP_KEY, keep="first")
    unique = df[~dup_mask].copy()
    dupes = df[dup_mask].copy()
    if not dupes.empty:
        dupes["rejection_reason"] = "duplicate (order_id, item_sku)"
    return unique, dupes


def publish_stage_to_final(config_path: str, input_path: str) -> tuple[int, int]:
    cfg = json.loads(Path(config_path).read_text())
    engine = create_engine(
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    )
    input_file_name = os.path.basename(input_path)

    existing = pd.read_sql(
        text("SELECT 1 FROM clean_orders WHERE input_file_name = :f LIMIT 1"),
        engine, params={"f": input_file_name},
    )
    if not existing.empty:
        print(f"[SKIP] '{input_file_name}' already finalized.")
        return (0, 0)

    stage = pd.read_sql(
        text("SELECT " + ", ".join(STAGE_COLUMNS)
             + " FROM stage_orders WHERE input_file_name = :f"),
        engine, params={"f": input_file_name},
    )
    valid, rejected = split_records(stage)
    valid, br_bad   = split_business_rules(valid)
    if not br_bad.empty:
        rejected = pd.concat([rejected, br_bad], ignore_index=True)
    valid, dupes = split_duplicates(valid)
    if not dupes.empty:
        rejected = pd.concat([rejected, dupes], ignore_index=True)

    if not valid.empty:
        out = valid.copy()
        out["input_file_name"] = input_file_name
        out.to_sql("clean_orders", engine, if_exists="append", index=False)

    if not rejected.empty:
        # Pull lossless raw text for the rejected rows.
        ids = [int(x) for x in rejected["source_row_id"].tolist()]
        stmt = text("SELECT * FROM raw_orders WHERE source_row_id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        )
        raw = pd.read_sql(stmt, engine, params={"ids": ids})
        out = raw.merge(
            rejected[["source_row_id", "rejection_reason"]], on="source_row_id", how="inner"
        )
        out["input_file_name"] = input_file_name
        out = out.drop(columns=["create_ts"], errors="ignore")
        out.to_sql("rejected_orders", engine, if_exists="append", index=False)

    print(f"[OK] {input_file_name}: {len(valid)} valid, {len(rejected)} rejected.")
    return (len(valid), len(rejected))


def main() -> int:
    parser = ArgumentParser(description="Finalize stage_orders -> clean_orders + rejected_orders.")
    parser.add_argument("--config", required=True, help="Path to MySQL config JSON file")
    parser.add_argument("--input",  required=True, help="Path to the original CSV (basename used as lookup key)")
    args = parser.parse_args()
    publish_stage_to_final(args.config, args.input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
