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
import sys
from pathlib import Path
logger = logging.getLogger(__name__)

# ── Resolve great_expectations/ on the host volume path ──────────
# docker-compose.yml mounts the repo root into the Airflow containers:
#   ./great_expectations:/opt/airflow/great_expectations
# We need to add that path so Python can import from it.
GX_MODULE_PATH = Path("/opt/airflow/great_expectations")

def run_gx_checkpoint(table_name: str) -> None:
    """
    Run the Great Expectations checkpoint for a single table.

    Delegates to great_expectations/gx_runner.main() after injecting
    the module path. Exits with sys.exit(1) on failure, which causes
    the Airflow PythonOperator task to be marked as FAILED.

    Args:
        table_name: One of the keys in great_expectations/config.SUITE_REGISTRY.
                    e.g. "olist_orders", "olist_order_reviews", "olist_order_items"

    Raises:
        ImportError: great_expectations/ not mounted at expected path.
        SystemExit(1): GX checkpoint failed or unhandled exception in gx_runner.
    """
    if not GX_MODULE_PATH.exists():
        raise ImportError(
            f"great_expectations module not found at {GX_MODULE_PATH}. "
            "Check docker-compose.yml volume: ./great_expectations:/opt/airflow/great_expectations"
        )

    if str(GX_MODULE_PATH) not in sys.path:
        sys.path.insert(0, str(GX_MODULE_PATH))
        logger.info(f"Injected {GX_MODULE_PATH} into sys.path")

    # Import after path injection — must be inside the function
    # so Airflow's DAG parser doesn't fail on import if the volume
    # isn't mounted yet when the scheduler first scans dags/.
    try:
        import gx_runner as real_runner  # great_expectations/gx_runner.py
    except ImportError as e:
        raise ImportError(
            f"Failed to import great_expectations/gx_runner.py: {e}. "
            "Verify the volume mount and that great_expectations/requirements.txt is installed."
        ) from e

    logger.info(f"Running GX checkpoint for: {table_name}")
    # Simulate CLI: inject --table arg then call main()
    sys.argv = ["gx_runner.py", "--table", table_name]
    real_runner.main()  # exits via sys.exit(0) on pass, sys.exit(1) on fail