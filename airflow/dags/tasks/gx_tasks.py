# ─────────────────────────────────────────────────────────────────
# tasks/gx_tasks.py — Great Expectations task definitions
#
# Exports one factory function:
#   make_gx_task(table_name) → PythonOperator that calls gx_runner
#
# Current state (Feature 2.3 — Epic 2):
#   gx_runner.run_checkpoint() is a STUB that raises NotImplementedError.
#   The GX expectation suites and checkpoints are built in Feature 2.2.
#   The stub is intentional — it proves the DAG wiring is correct
#   (Airflow calls the function, the function fails loudly, the task
#   turns red) without requiring GX to be fully set up first.
#
# Feature 2.2 upgrade path:
#   When gx/gx_runner.py is fully implemented, replace the import stub
#   in gx/gx_runner.py with real GX checkpoint execution.
#   No changes needed in this file or in dag.py.
#
# Why PythonOperator (not BashOperator) for GX?
#   GX runs as a Python library call — there is no CLI command that
#   runs a checkpoint and returns a structured pass/fail result.
#   PythonOperator lets us import gx_runner directly, catch GX
#   ValidationFailedError cleanly, and surface a clear error message
#   in the Airflow task log. BashOperator would require subprocess
#   management and lose the structured exception context.
# ─────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging

from airflow.operators.python import PythonOperator

from config import GX_TABLES

logger = logging.getLogger(__name__)


def _run_gx_checkpoint(table_name: str) -> None:
    """
    Callable passed to PythonOperator — runs one GX checkpoint.

    Imports gx_runner at call time (not at module import time) so
    that Airflow can parse the DAG file even when the GX library
    is not yet installed. The import error surfaces in the task log,
    not in the DAG parse log.

    Args:
        table_name: The Olist table to validate (e.g. "olist_orders").
                    Must match an expectation suite in gx/gx_runner.py.

    Raises:
        NotImplementedError: GX runner is a stub in Feature 2.3.
        ImportError: GX or gx_runner is not installed/available.
        RuntimeError: GX checkpoint failed — data did not meet expectations.
    """
    logger.info(f"Running GX checkpoint for table: {table_name}")

    try:
        # Lazy import — gx_runner lives at airflow/dags/gx/gx_runner.py
        # Fully implemented in Feature 2.2; stub until then.
        from gx.gx_runner import run_checkpoint  # type: ignore[import]
    except ImportError as e:
        raise ImportError(
            f"Cannot import gx_runner for table '{table_name}'. "
            "Ensure Feature 2.2 is complete and gx/gx_runner.py exists "
            f"at airflow/dags/gx/gx_runner.py. Original error: {e}"
        ) from e

    run_checkpoint(table_name=table_name)
    logger.info(f"GX checkpoint passed for table: {table_name} ✓")


def make_gx_task(table_name: str) -> PythonOperator:
    """
    Factory: create one GX validation task for the given table.

    Called three times in dag.py — once per table in GX_TABLES.
    All three tasks are placed inside a TaskGroup('data_quality')
    and run in parallel after run_glue_etl, before load_to_redshift.

    Args:
        table_name: One of the values in config.GX_TABLES.

    Returns:
        PythonOperator task object.
    """
    if table_name not in GX_TABLES:
        raise ValueError(
            f"'{table_name}' is not in config.GX_TABLES. "
            f"Valid tables: {GX_TABLES}"
        )

    # task_id uses underscores — Airflow requires no dots or hyphens in task IDs
    safe_name = table_name.replace("-", "_")

    return PythonOperator(
        task_id         = f"run_gx_{safe_name}",
        python_callable = _run_gx_checkpoint,
        # op_kwargs are passed as keyword arguments to _run_gx_checkpoint
        op_kwargs       = {"table_name": table_name},
    )
