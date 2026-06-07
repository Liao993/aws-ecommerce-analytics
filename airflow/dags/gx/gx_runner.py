# ─────────────────────────────────────────────────────────────────
# gx/gx_runner.py — Great Expectations checkpoint runner (STUB)
#
# Status: STUB — Feature 2.3 (Airflow wiring).
# Full implementation: Feature 2.2 (Great Expectations setup).
#
# This stub exists so the Airflow DAG can be wired and tested
# without GX being fully set up. The PythonOperator in gx_tasks.py
# imports and calls run_checkpoint() — this stub causes the GX tasks
# to fail loudly with NotImplementedError, which is the correct
# behaviour for an unimplemented feature gate.
#
# Feature 2.2 implementation contract:
#   run_checkpoint(table_name) must:
#   - Load the GX DataContext from great_expectations/
#   - Run the checkpoint named f"{table_name}_checkpoint"
#   - Raise RuntimeError if any expectation fails (do NOT return False)
#   - Log the HTML Data Docs URL to S3 on success
#   - Return None on success
# ─────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_checkpoint(table_name: str) -> None:
    """
    Run the Great Expectations checkpoint for one Olist table.

    STUB — raises NotImplementedError until Feature 2.2 is complete.

    Args:
        table_name: The Olist table to validate, e.g. "olist_orders".
                    Must match a checkpoint defined in great_expectations/.

    Raises:
        NotImplementedError: Always, until Feature 2.2 replaces this stub.
    """
    logger.warning(
        f"gx_runner.run_checkpoint('{table_name}') called but GX is not yet "
        "implemented. This is expected in Feature 2.3. "
        "Implement Feature 2.2 to activate this gate."
    )

    raise NotImplementedError(
        f"GX checkpoint for '{table_name}' is not yet implemented. "
        "Complete Feature 2.2 (Great Expectations setup) and replace "
        "this stub with real checkpoint execution. "
        "See airflow/dags/gx/gx_runner.py for the implementation contract."
    )
