"""
backend/redshift_connection.py — Redshift connection layer

Single responsibility: open a Redshift connection and execute SQL.
No business logic, no chart logic, no Streamlit UI code lives here —
just "how do we talk to the database."

Auth pattern:
    boto3 calls the Redshift Serverless GetCredentials API, which returns
    a short-lived db_user + db_password pair (valid 900 seconds). This
    exercises the olist-readonly-role provisioned in Terraform — the
    dashboard never holds a long-lived Redshift password.
"""

import os
import logging

import boto3 # type: ignore
import pandas as pd # type: ignore
import redshift_connector # type: ignore

logger = logging.getLogger(__name__)

# ── Connection constants ──────────────────────────────────────────
REDSHIFT_HOST = os.getenv("REDSHIFT_HOST")
REDSHIFT_DB = os.getenv("REDSHIFT_DB", "dev")
REDSHIFT_PORT = int(os.getenv("REDSHIFT_PORT", "5439"))
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ca-central-1")
WORKGROUP = "olist-workgroup"


def get_redshift_connection() -> redshift_connector.Connection:
    """
    Open a Redshift connection using IAM temporary credentials.

    Returns:
        redshift_connector.Connection — caller is responsible for closing it.

    Raises:
        botocore.exceptions.ClientError: IAM role lacks redshift-serverless:GetCredentials,
            or the workgroup name is wrong.
        redshift_connector.Error: Network/auth failure connecting to Redshift itself.
    """
    client = boto3.client("redshift-serverless", region_name=AWS_REGION)
    creds = client.get_credentials(workgroupName=WORKGROUP, dbName=REDSHIFT_DB)

    return redshift_connector.connect(
        host=REDSHIFT_HOST,
        port=REDSHIFT_PORT,
        database=REDSHIFT_DB,
        user=creds["dbUser"],
        password=creds["dbPassword"],
    )


def run_query(sql: str) -> pd.DataFrame:
    """
    Execute a SQL string against Redshift and return the result as a DataFrame.

    Opens a fresh connection per call (short-lived IAM creds make connection
    pooling more complexity than it's worth at this dashboard's query volume)
    and always closes it, even on error.

    Args:
        sql: Full SQL statement to execute. Caller owns SQL safety — this
             dashboard only ever issues hardcoded SELECT statements, no
             user-supplied input is interpolated into queries.

    Returns:
        pandas DataFrame with query results. Columns named from cursor.description.

    Raises:
        redshift_connector.Error: Query failed (bad SQL, missing table, etc.)
    """
    conn = get_redshift_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()
