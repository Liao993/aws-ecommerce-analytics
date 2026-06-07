# ─────────────────────────────────────────────────────────────────
# tasks/gx_tasks.py — Great Expectations task definitions
#
# Exports one factory function:
#   make_gx_task(table_name) → BashOperator that runs gx_runner in olist_gx
#
# Why BashOperator here?
#   The GX dependencies are installed in the olist_gx container, not
#   the Airflow scheduler image. Airflow only orchestrates the command.
# ─────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging

from airflow.operators.bash import BashOperator # type: ignore

from config import GX_CONTAINER_NAME

logger = logging.getLogger(__name__)



def make_gx_task(table_name: str) -> BashOperator:
    """
    Create a BashOperator that runs the GX checkpoint for one table.

    Args:
        table_name: e.g. "olist_orders" — must be in SUITE_REGISTRY.

    Returns:
        BashOperator — fails the task (and blocks downstream) if GX fails.
    """
    return BashOperator(
        task_id=f"run_gx_{table_name}",
        bash_command=(
            f"docker exec {GX_CONTAINER_NAME} "
            f"python gx_runner.py --table {table_name}"
        ),
    )
