# ─────────────────────────────────────────────────────────────────
# tasks/dbt_tasks.py — dbt task definitions
#
# Exports factory functions for each dbt pipeline stage:
#   make_dbt_staging_task()      → BashOperator: dbt run --select staging
#   make_dbt_intermediate_task() → BashOperator: dbt run --select intermediate
#   make_dbt_marts_task()        → BashOperator: dbt run --select marts
#   make_dbt_snapshot_task()     → BashOperator: dbt snapshot
#
# Execution pattern — docker exec:
#   dbt runs INSIDE the olist_dbt container (defined in docker-compose.yml).
#   Airflow calls `docker exec olist_dbt dbt run ...` from inside its own
#   container. Both containers share the same Docker network (olist_network),
#   so the exec call reaches the dbt container's Unix socket via the mounted
#   Docker socket (/var/run/docker.sock).
#
# Why docker exec instead of installing dbt in the Airflow image?
#   1. Single source of truth — dbt version and profiles.yml live in one place.
#   2. No dependency conflicts — Airflow's Python env stays clean.
#   3. Clean prod migration — swap docker exec for KubernetesPodOperator
#      in Epic 7 without touching this file's logic.
#   4. Debuggable — you can run the exact same `docker exec` command
#      from your terminal to reproduce what Airflow does.
#
# Docker socket requirement:
#   The Airflow container must mount the host Docker socket:
#     volumes:
#       - /var/run/docker.sock:/var/run/docker.sock
#   This is set in airflow/docker-compose.yml.
#   Without it, `docker exec` will fail with "Cannot connect to Docker daemon".
#
# AWS auth:
#   dbt connects to Redshift using profiles.yml mounted at ~/.dbt/profiles.yml
#   inside the dbt container. Credentials come from .env via docker-compose.yml.
#   No AWS credentials needed in this file.
# ─────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging

from airflow.operators.bash import BashOperator # type: ignore

from config import DBT_CONFIG, DBT_SELECTORS

logger = logging.getLogger(__name__)


def _dbt_run_command(selector: str) -> str:
    """
    Build the full docker exec command for `dbt run --select <selector>`.

    Args:
        selector: dbt node selector, e.g. "staging", "intermediate", "marts".

    Returns:
        Shell command string passed to BashOperator's bash_command.
    """
    container    = DBT_CONFIG["container"]
    project_dir  = DBT_CONFIG["project_dir"]
    profiles_dir = DBT_CONFIG["profiles_dir"]
    target       = DBT_CONFIG["target"]

    return (
        f"docker exec {container} "
        f"dbt run "
        f"--select {selector} "
        f"--project-dir {project_dir} "
        f"--profiles-dir {profiles_dir} "
        f"--target {target}"
    )


def _dbt_snapshot_command() -> str:
    """
    Build the full docker exec command for `dbt snapshot`.

    Returns:
        Shell command string for BashOperator.
    """
    container    = DBT_CONFIG["container"]
    project_dir  = DBT_CONFIG["project_dir"]
    profiles_dir = DBT_CONFIG["profiles_dir"]
    target       = DBT_CONFIG["target"]

    return (
        f"docker exec {container} "
        f"dbt snapshot "
        f"--project-dir {project_dir} "
        f"--profiles-dir {profiles_dir} "
        f"--target {target}"
    )


def make_dbt_staging_task() -> BashOperator:
    """
    Task 7: Run all dbt staging models.

    Staging models read from dev_raw Redshift schema (loaded by Glue),
    rename columns, cast types, and add surrogate keys. Materialized as
    views — no storage cost, always reflects latest Glue load.

    Returns:
        BashOperator task object.
    """
    return BashOperator(
        task_id      = "dbt_staging",
        bash_command = _dbt_run_command(DBT_SELECTORS["staging"]),
    )


def make_dbt_intermediate_task() -> BashOperator:
    """
    Task 8: Run all dbt intermediate models.

    Intermediate models join staging tables and compute business metrics
    (delivery delay, total order value, freight percentage). Materialized
    as views. Must run after staging models are green.

    Returns:
        BashOperator task object.
    """
    return BashOperator(
        task_id      = "dbt_intermediate",
        bash_command = _dbt_run_command(DBT_SELECTORS["intermediate"]),
    )


def make_dbt_marts_task() -> BashOperator:
    """
    Task 9: Run all dbt mart models.

    Mart models are the final analytical layer — seller performance,
    customer cohorts, RFM segmentation, delivery analysis. Materialized
    as tables (not views) so Streamlit queries run fast without scanning
    all upstream joins on every page load.

    Returns:
        BashOperator task object.
    """
    return BashOperator(
        task_id      = "dbt_marts",
        bash_command = _dbt_run_command(DBT_SELECTORS["marts"]),
    )


def make_dbt_snapshot_task() -> BashOperator:
    """
    Task 10: Run dbt snapshots.

    Snapshots track slowly changing dimensions — customers and sellers.
    Each run appends new rows with dbt_valid_from / dbt_valid_to populated.
    Must run last — snapshots read from mart models in some configurations
    and should capture the fully-refreshed state.

    Returns:
        BashOperator task object.
    """
    return BashOperator(
        task_id      = "dbt_snapshot",
        bash_command = _dbt_snapshot_command(),
    )

# ADD THIS at the bottom of airflow/dags/tasks/dbt_tasks.py

def make_dbt_source_freshness_task() -> BashOperator:
    """
    Task 6.5: Run dbt source freshness check.

    Checks MAX(loaded_at_field) on each configured source table and compares
    it to NOW(). If data is too old, dbt raises a warning or error.

    For this project (static Olist 2016–2018 data): freshness will always WARN
    because the data is years old. This is correct and expected — the check is
    configured to demonstrate the pattern. In production, this would be the
    first gate in the pipeline: if freshness fails, dbt run never executes.

    The trailing `|| true` means a WARN/ERROR from freshness does not block
    downstream Airflow tasks on this historical dataset. Remove `|| true` in
    a production pipeline where data is live.

    Returns:
        BashOperator task object.
    """
    container    = DBT_CONFIG["container"]
    project_dir  = DBT_CONFIG["project_dir"]
    profiles_dir = DBT_CONFIG["profiles_dir"]
    target       = DBT_CONFIG["target"]

    return BashOperator(
        task_id      = "dbt_source_freshness",
        bash_command = (
            f"docker exec {container} "
            f"dbt source freshness "
            f"--project-dir {project_dir} "
            f"--profiles-dir {profiles_dir} "
            f"--target {target} "
            f"|| true"
            # || true: freshness always WARNs on historical Olist data (2016-2018).
            # This prevents Airflow from blocking the pipeline on expected warnings.
            # In production with live data, remove || true — freshness should be blocking.
        ),
    )


def make_dbt_test_task() -> BashOperator:
    """
    Task 11: Run the full dbt test suite across all layers.

    Runs dbt test with no selector — covers staging, intermediate, and marts.
    Placed at the end of the pipeline so all models are materialized before
    tests run. Fails the Airflow task (and blocks nothing downstream, since
    this is the last task) if any test fails.

    Returns:
        BashOperator task object.
    """
    container    = DBT_CONFIG["container"]
    project_dir  = DBT_CONFIG["project_dir"]
    profiles_dir = DBT_CONFIG["profiles_dir"]
    target       = DBT_CONFIG["target"]

    return BashOperator(
        task_id      = "dbt_test_all_layers",
        bash_command = (
            f"docker exec {container} "
            f"dbt test "
            f"--project-dir {project_dir} "
            f"--profiles-dir {profiles_dir} "
            f"--target {target}"
        ),
    )