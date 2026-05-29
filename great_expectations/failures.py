"""
failures.py — GX failure summary writer

Single responsibility: extract failed expectations from a CheckpointResult
and write a structured JSON audit record to S3.

Called by gx_runner.py only when result.success is False. Provides a
queryable, timestamped failure trail in S3 without requiring CloudWatch
log access — useful for debugging and for interview discussions about
production observability.
"""

import json
import logging
from datetime import datetime, timezone

import boto3 # type: ignore

from config import S3_BUCKET, S3_FAILURES_PREFIX

logger = logging.getLogger(__name__)


def write_failure_summary(
    table_name: str,
    result,
    aws_region: str,
) -> None:
    """
    Parse the checkpoint result for failed expectations and write a JSON
    summary to S3.

    S3 key pattern:
        dev/analytics/gx-failures/{table_name}/{YYYYMMDDTHHMMSSZ}.json

    The timestamp in the key makes every failure run its own object —
    no overwriting, full audit history retained automatically.

    JSON structure:
        {
            "table":         "olist_orders",
            "run_time":      "2026-05-28T14:32:01+00:00",
            "total_failed":  2,
            "failures": [
                {
                    "expectation_type": "expect_column_values_to_not_be_null",
                    "kwargs":           {"column": "order_id"},
                    "observed_value":   "42",
                    "exception_info":   null
                },
                ...
            ]
        }

    Each failed expectation is also logged at ERROR level so it appears
    in CloudWatch Logs for the Airflow task run.

    Args:
        table_name: Table being validated — used in the S3 key and summary body.
        result:     CheckpointResult from checkpoint.run_checkpoint().
        aws_region: AWS region string.
    """
    failed_expectations = []

    for validation_result in result.run_results.values():
        for r in validation_result["validation_result"].results:
            if r.success:
                continue

            failed_expectations.append({
                "expectation_type": r.expectation_config.expectation_type,
                "kwargs":           r.expectation_config.kwargs,
                "observed_value":   str(r.result.get("observed_value", "N/A")),
                "exception_info":   r.exception_info if hasattr(r, "exception_info") else None,
            })

            logger.error(
                f"  FAILED: {r.expectation_config.expectation_type} | "
                f"kwargs={r.expectation_config.kwargs} | "
                f"observed={r.result.get('observed_value', 'N/A')}"
            )

    summary = {
        "table":        table_name,
        "run_time":     datetime.now(timezone.utc).isoformat(),
        "total_failed": len(failed_expectations),
        "failures":     failed_expectations,
    }

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    s3_key = f"{S3_FAILURES_PREFIX}/{table_name}/{timestamp_str}.json"

    s3 = boto3.client("s3", region_name=aws_region)
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=json.dumps(summary, indent=2),
        ContentType="application/json",
    )

    logger.error(
        f"Failure summary ({len(failed_expectations)} failed expectations) "
        f"written → s3://{S3_BUCKET}/{s3_key}"
    )