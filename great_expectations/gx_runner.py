"""
gx_runner.py — Great Expectations pipeline entry point

Usage:
    python gx_runner.py --table olist_orders
    python gx_runner.py --table olist_order_reviews
    python gx_runner.py --table olist_order_items

Responsibilities of this file (only):
    - Parse CLI arguments
    - Set up logging (consistent with Glue job main.py pattern in this repo)
    - Load .env credentials
    - Orchestrate the four pipeline steps in order:
        reader     → read Parquet from S3
        checkpoint → build GX context, run validation
        docs       → upload HTML Data Docs to S3
        failures   → write failure JSON to S3 (only on fail)
    - Exit with code 0 (pass) or 1 (fail / unhandled error)

All business logic lives in the imported modules — this file contains
no GX, no S3, no pandas. One file, one job.

Exit codes:
    0  — all expectations passed
    1  — one or more expectations failed OR unhandled exception
"""

import argparse
import logging
import os
import sys
import tempfile

from dotenv import load_dotenv # type: ignore

from config import SUITE_REGISTRY, AWS_REGION_DEFAULT
from reader import read_parquet_from_s3
from checkpoint import load_suite_configs, run_checkpoint
from docs import upload_docs_to_s3
from failures import write_failure_summary

# ─────────────────────────────────────────────────────────────────
# Logging — same format as Glue job main.py files in this repo
# ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────

def main() -> None:
    # Load .env so AWS credentials are available to all modules
    load_dotenv()
    aws_region = os.getenv("AWS_DEFAULT_REGION", AWS_REGION_DEFAULT)

    parser = argparse.ArgumentParser(
        description="Run Great Expectations checkpoint for a processed Olist table."
    )
    parser.add_argument(
        "--table",
        required=True,
        choices=list(SUITE_REGISTRY.keys()),
        help="Table name to validate.",
    )
    args = parser.parse_args()
    table_name = args.table

    logger.info("=" * 60)
    logger.info(f"GX runner starting — table: {table_name}")
    logger.info("=" * 60)

    with tempfile.TemporaryDirectory(prefix="gx_docs_") as tmp_docs_dir:
        try:
            # Step 1 — Read
            df = read_parquet_from_s3(table_name, aws_region)

            # Step 2 — Load suite configs + run checkpoint
            suite_configs = load_suite_configs(table_name)
            result = run_checkpoint(df, table_name, suite_configs, tmp_docs_dir)

            # Step 3 — Upload Data Docs to S3 (always, pass or fail)
            upload_docs_to_s3(tmp_docs_dir, aws_region)

            # Step 4 — Handle failures
            if not result.success:
                logger.error(f"Checkpoint FAILED for {table_name}")
                write_failure_summary(table_name, result, aws_region)
                logger.error("Exiting with code 1 — Airflow will mark this task as failed.")
                sys.exit(1)

            logger.info(f"All expectations PASSED for {table_name} ✓")

        except Exception as e:
            logger.exception(f"Unhandled error during GX run for {table_name}: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
