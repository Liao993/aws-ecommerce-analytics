"""
docs.py — Data Docs S3 uploader

Single responsibility: walk a local Data Docs directory tree (written by
GX during checkpoint.run()) and upload every file to S3.

Called by gx_runner.py after run_checkpoint() returns, regardless of
whether the checkpoint passed or failed — you always want fresh HTML docs.
"""

import logging
from pathlib import Path

import boto3 # type: ignore

from config import S3_BUCKET, S3_DOCS_PREFIX

logger = logging.getLogger(__name__)


def upload_docs_to_s3(local_docs_dir: str, aws_region: str) -> None:
    s3 = boto3.client("s3", region_name=aws_region)
    docs_path = Path(local_docs_dir)
    uploaded = 0

    all_files = list(docs_path.rglob("*"))
    if not any(f.is_file() for f in all_files):
        logger.warning(
            f"upload_docs_to_s3: no files found in {local_docs_dir} — "
            "Data Docs were not written. Check checkpoint.py site redirect."
        )
        return

    # Strip trailing slash from prefix to avoid double-slash S3 keys
    prefix = S3_DOCS_PREFIX.rstrip("/")

    for file_path in all_files:
        if not file_path.is_file():
            continue

        relative_key = file_path.relative_to(docs_path)
        s3_key = f"{prefix}/{relative_key}"
        content_type = "text/html" if file_path.suffix == ".html" else "application/octet-stream"

        s3.upload_file(
            Filename=str(file_path),
            Bucket=S3_BUCKET,
            Key=s3_key,
            ExtraArgs={"ContentType": content_type},
        )
        uploaded += 1

    logger.info(f"Uploaded {uploaded} Data Docs files → s3://{S3_BUCKET}/{prefix}/")