# ─────────────────────────────────────────────────────────────────
# callbacks/notify.py — DAG failure callback
#
# Called by Airflow when any task in olist_daily_pipeline fails.
# Passed as on_failure_callback in the DAG default_args.
#
# Current behaviour (Epic 2):
#   Logs the failure context and raises an exception so Airflow
#   marks the task red in the Graph View and stops the DAG run.
#   No external notification is sent yet.
#
# Epic 5 upgrade path:
#   Replace the body of notify_on_failure with an SNS publish call:
#       sns_client.publish(
#           TopicArn=SNS_TOPIC_ARN,
#           Subject=f"[OLIST] Pipeline failure: {task_id}",
#           Message=message,
#       )
#   Add SNS_TOPIC_ARN to config.py when that step is implemented.
#
# Airflow callback contract:
#   Airflow calls this function with a single argument: `context`,
#   a dict containing the task instance, DAG run, execution date,
#   exception, and other metadata. The function must not return a value.
# ─────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def notify_on_failure(context: dict[str, Any]) -> None:
    """
    on_failure_callback for olist_daily_pipeline.

    Logs structured failure context and raises a RuntimeError so the
    Airflow Graph View marks the failed task clearly — no silent pass-through.

    Args:
        context: Airflow task context dict, injected automatically.
                 Key fields used: dag_id, task_id, execution_date, exception.

    Raises:
        RuntimeError: Always — signals Airflow to mark this callback as failed
                      and halts downstream tasks in the current DAG run.
    """
    dag_id        = context.get("dag").dag_id if context.get("dag") else "unknown_dag"
    task_id       = context.get("task_instance").task_id if context.get("task_instance") else "unknown_task"
    execution_date = context.get("execution_date", "unknown_date")
    exception     = context.get("exception", "no exception captured")

    message = (
        f"[OLIST PIPELINE FAILURE]\n"
        f"  DAG:            {dag_id}\n"
        f"  Task:           {task_id}\n"
        f"  Execution Date: {execution_date}\n"
        f"  Exception:      {exception}\n"
        f"\n"
        f"  → Check the task log in Airflow UI for full traceback.\n"
        f"  → Epic 5: replace this stub with SNS publish to alert on failure."
    )

    logger.error(message)

    # Raise so Airflow marks this callback run as failed in the UI.
    # Without this, a logging-only callback silently passes, which is
    # confusing — the task shows red but the callback row shows green.
    raise RuntimeError(
        f"Pipeline failure in {dag_id}.{task_id} at {execution_date}. "
        "See Airflow task log for details. (SNS notification pending Epic 5.)"
    )
