"""
Step 1 — Raw ingest.

Reads a CSV file and inserts every row as TEXT into `raw_orders`,
adding two audit columns:
    create_ts        - server timestamp (DEFAULT CURRENT_TIMESTAMP)
    input_file_name  - the file's basename

Idempotency: if any row with the same input_file_name already exists,
the file is skipped (no duplicates).

Usage:
    python -m src.csv_to_raw --config config.json --input /full/path/to/input.csv

config.json shape:
    {
      "host":     "localhost",
      "port":     3306,
      "user":     "root",
      "password": "...",
      "database": "manulife_takehome"
    }
"""

import json
import os
import sys
from argparse import ArgumentParser
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine


CSV_COLUMNS = (
    "order_id", "customer_id", "customer_name", "email", "phone",
    "country", "state", "city", "address", "postal_code",
    "order_date", "ship_date", "ship_mode",
    "item_sku", "item_name", "quantity", "unit_price", "currency",
    "discount_code", "order_notes",
)


def load_csv_to_raw(config_path: str, input_path: str) -> int:
    cfg = json.loads(Path(config_path).read_text())
    connection_string = f"mysql+pymysql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    engine = create_engine(connection_string)

    file_name = os.path.basename(input_path)

    check_sql = "SELECT input_file_name FROM raw_orders WHERE input_file_name = %(f)s LIMIT 1"
    existing = pd.read_sql(check_sql, engine, params={"f": file_name})
    if len(existing) > 0:
        print(f"[SKIP] '{file_name}' already loaded in raw_orders.")
        return 0

    # Read every cell as a string so nothing is silently coerced
    # (no NaN on '', no float on '89,99', no NaT on weird dates).
    df = pd.read_csv(
        input_path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )

    df = df[list(CSV_COLUMNS)]
    df.insert(0, "input_file_name", file_name)
    # create_ts is filled by MySQL DEFAULT CURRENT_TIMESTAMP; we don't set it.

    df.to_sql(
        name="raw_orders",
        con=engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    print(f"[OK] Loaded {len(df)} rows from '{file_name}' into raw_orders.")
    return len(df)


def main() -> int:
    parser = ArgumentParser(description="Load CSV into raw_orders.")
    parser.add_argument("--config", required=True, help="Path to MySQL config JSON file")
    parser.add_argument("--input",  required=True, help="Full path to input CSV file")
    args = parser.parse_args()

    load_csv_to_raw(args.config, args.input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
