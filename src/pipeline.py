"""
Convenience wrapper - runs csv_to_raw -> raw_to_stage -> stage_to_published in order.

In production these would be three separate orchestrator tasks
(Airflow, Step Functions, etc.) with explicit dependencies.

Usage:
    python -m src.pipeline --config config.json --input /full/path/to/input.csv
"""

import sys
from argparse import ArgumentParser

from src.csv_to_raw import load_csv_to_raw
from src.raw_to_stage import transform_raw_to_stage
from src.stage_to_published import publish_stage_to_final


def run(config_path: str, input_path: str) -> None:
    load_csv_to_raw(config_path, input_path)
    transform_raw_to_stage(config_path, input_path)
    publish_stage_to_final(config_path, input_path)


def main() -> int:
    parser = ArgumentParser(description="Run csv_to_raw + raw_to_stage + stage_to_published end to end.")
    parser.add_argument("--config", required=True, help="Path to MySQL config JSON file")
    parser.add_argument("--input", required=True, help="Full path to input CSV file")
    args = parser.parse_args()
    run(args.config, args.input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
