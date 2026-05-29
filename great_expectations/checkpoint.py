"""
checkpoint.py — GX context + checkpoint runner

Single responsibility: given a DataFrame and expectation configs, build
an ephemeral GX context, register the suite, and run the checkpoint.

Does NOT read data (reader.py) and does NOT write HTML or JSON (docs.py,
failures.py). Returns the raw CheckpointResult for callers to inspect.

Called by gx_runner.py after reading data and loading suite configs.
"""

import importlib
import logging

import pandas as pd # type: ignore
import great_expectations as gx
from great_expectations.core.expectation_configuration import ExpectationConfiguration # type: ignore

from config import SUITE_REGISTRY

logger = logging.getLogger(__name__)


def load_suite_configs(table_name: str) -> list[dict]:
    """
    Dynamically import the suite module for this table and return its
    expectation config list.

    Each suite module exposes a single public function:
        get_expectation_configs() -> list[dict]

    where each dict is:
        {"expectation_type": "expect_column_values_to_not_be_null", "kwargs": {"column": "order_id"}}

    This keeps checkpoint.py fully decoupled from suite details — adding
    a new table only requires a new suite file + one line in SUITE_REGISTRY.

    Args:
        table_name: Must be a key in SUITE_REGISTRY.

    Returns:
        List of expectation config dicts from the suite module.

    Raises:
        ValueError: table_name not registered.
        AttributeError: Suite module missing get_expectation_configs().
    """
    module_path = SUITE_REGISTRY.get(table_name)
    if not module_path:
        raise ValueError(
            f"No expectation suite registered for '{table_name}'. "
            f"Available: {list(SUITE_REGISTRY.keys())}"
        )

    logger.info(f"Importing suite module: {module_path}")
    module = importlib.import_module(module_path)
    configs = module.get_expectation_configs()
    logger.info(f"Loaded {len(configs)} expectations for {table_name}")
    return configs


def run_checkpoint(
    df: pd.DataFrame,
    table_name: str,
    suite_configs: list[dict],
    docs_output_dir: str,
):
    """
    Build an ephemeral GX context, register the expectation suite, and
    run the checkpoint against the provided DataFrame.

    Uses EphemeralDataContext so no great_expectations.yml or store
    directories are written to disk. Everything lives in memory for the
    duration of this function call.

    The local filesystem Data Docs site is configured here (pointing at
    docs_output_dir) because GX needs a site registered before
    build_data_docs() can be called. The actual HTML build + S3 upload
    is handled separately by docs.py.

    Args:
        df:              Validated DataFrame (output of reader.read_parquet_from_s3).
        table_name:      Used to name the datasource, suite, and checkpoint.
        suite_configs:   Expectation config dicts from load_suite_configs().
        docs_output_dir: Local temp directory where GX writes HTML Data Docs.

    Returns:
        GX CheckpointResult — callers check result.success to decide next steps.
    """
    logger.info(f"Building ephemeral GX context for {table_name}")
    context = gx.get_context(mode="ephemeral")

    # Register a local Data Docs site so build_data_docs() has somewhere to write.
    # docs.py will upload this directory tree to S3 after this function returns.
    context.config.data_docs_sites["local_site"]["store_backend"]["base_directory"] = docs_output_dir
    logger.info(f"Data Docs site redirected → {docs_output_dir}")
    # ── Pandas datasource ──────────────────────────────────────────
    datasource = context.sources.add_pandas(name=f"{table_name}_datasource")
    data_asset = datasource.add_dataframe_asset(name=f"{table_name}_asset")
    batch_request = data_asset.build_batch_request(dataframe=df)

    # ── Expectation suite ──────────────────────────────────────────
    suite_name = f"{table_name}_suite"
    suite = context.add_expectation_suite(expectation_suite_name=suite_name)

    for cfg in suite_configs:
        suite.add_expectation(
            ExpectationConfiguration(
                expectation_type=cfg["expectation_type"],
                kwargs=cfg["kwargs"],
            )
        )

    context.save_expectation_suite(suite)
    logger.info(f"Suite '{suite_name}' saved with {len(suite_configs)} expectations")

    # ── Checkpoint ─────────────────────────────────────────────────
    checkpoint = context.add_or_update_checkpoint(
        name=f"{table_name}_checkpoint",
        validations=[
            {
                "batch_request": batch_request,
                "expectation_suite_name": suite_name,
            }
        ],
    )

    logger.info(f"Running checkpoint for {table_name}")
    result = checkpoint.run()

    # Build HTML into docs_output_dir now that validation results exist
    try:
        context.build_data_docs(site_names=["local_site"])
        logger.info(f"Data Docs HTML written to {docs_output_dir}")
    except Exception as e:
        # Non-fatal — log and continue. Docs upload will upload 0 files
        # but the failure JSON will still be written.
        logger.warning(f"build_data_docs failed (non-fatal): {e}")

    return result

    return result