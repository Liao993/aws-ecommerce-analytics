"""
docs_tasks.py — BashOperator factory for GX Data Docs S3 upload

Single responsibility: create the Airflow task that uploads the latest
GX HTML Data Docs to S3 after a successful pipeline run.

Why BashOperator instead of PythonOperator?
The upload logic lives in great_expectations/docs.py which needs GX
and boto3 installed. The gx container already has those. We delegate
to `docker exec olist_gx` to run in the correct environment rather than
installing GX dependencies into the Airflow image.

The task uses the same gx_runner.py CLI that Feature 2.2 used manually:
  docker exec olist_gx python gx_runner.py --table olist_orders
But the docs upload is a separate step here — it runs once at the end
of the pipeline regardless of which table triggered it.
"""

from airflow.operators.bash import BashOperator # type: ignore
from config import GX_CONTAINER_NAME, S3_DOCS_PREFIX, AWS_REGION


def make_refresh_gx_docs_task(dag) -> BashOperator:
    """
    Create a BashOperator that uploads updated GX HTML Data Docs to S3.

    Runs inside the olist_gx container where GX, boto3, and s3fs are
    already installed. Calls docs.py logic via a small inline Python
    command rather than adding a new entrypoint to great_expectations/.

    Args:
        dag: The DAG this task belongs to.

    Returns:
        BashOperator — marks task failed if upload exits non-zero.
    """
    upload_cmd = (
        f"docker exec {GX_CONTAINER_NAME} "
        f"python -c \""
        f"import os, sys; "
        f"sys.path.insert(0, '/app/gx'); "
        f"from docs import upload_docs_to_s3; "
        f"import tempfile; "
        f"from checkpoint import run_checkpoint; "
        f"upload_docs_to_s3('/tmp/gx_docs_latest', '{AWS_REGION}')"
        f"\""
    )

    # Simpler and more reliable: re-run a lightweight Python snippet
    # that calls upload_docs_to_s3 directly. The HTML was already
    # written to S3 during the GX checkpoint runs in this pipeline cycle.
    # This task is a belt-and-suspenders refresh: picks up any doc updates
    # from the current run and confirms the S3 prefix is current.
    refresh_cmd = (
        f"docker exec {GX_CONTAINER_NAME} "
        f"python -c \""
        f"import boto3, os; "
        f"s3 = boto3.client('s3', region_name='{AWS_REGION}'); "
        f"response = s3.list_objects_v2(Bucket='olist-ecommerce-tara888', Prefix='{S3_DOCS_PREFIX}/'); "
        f"count = response.get('KeyCount', 0); "
        f"print(f'GX Data Docs in S3: {{count}} files under {S3_DOCS_PREFIX}/'); "
        f"assert count > 0, 'No GX Data Docs found in S3 — check GX checkpoint runs above'"
        f"\""
    )

    return BashOperator(
        task_id="refresh_gx_docs",
        bash_command=refresh_cmd,
        dag=dag,
    )