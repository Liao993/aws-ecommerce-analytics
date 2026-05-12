# ─────────────────────────────────────────────────────────────────
# Provider
# ─────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      ManagedBy   = "terraform"
      Environment = "shared"
    }
  }
}

# ─────────────────────────────────────────────────────────────────
# Data source — current AWS account ID (used in IAM policy ARNs)
# ─────────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

# ─────────────────────────────────────────────────────────────────
# S3 — Data Lake Bucket
# ─────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "data_lake" {
  bucket = var.bucket_name

  tags = {
    Name = var.bucket_name
  }
}

# Block all public access — this is a private data lake
resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning — enables replay and recovery of raw source files
resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Prefix placeholder objects — S3 has no real "folders";
# zero-byte objects with a trailing slash simulate the structure
# so the console and Glue Crawlers see the expected layout.
locals {
  s3_prefixes = [
    "dev/raw/",
    "dev/processed/",
    "dev/analytics/",
    "dev/glue-scripts/",
    "prod/raw/",
    "prod/processed/",
    "prod/analytics/",
    "prod/glue-scripts/",
  ]
}

resource "aws_s3_object" "prefixes" {
  for_each = toset(local.s3_prefixes)

  bucket  = aws_s3_bucket.data_lake.id
  key     = each.value
  content = ""
}

# ─────────────────────────────────────────────────────────────────
# IAM — Trust policies
#
# assume_role_base       → shared by ae, junior_de, readonly
#                          allows IAM principals in this account only
#
# assume_role_admin      → admin role only, requires MFA
#
# assume_role_senior_de  → NEW (line 105–130): senior_de only
#                          allows IAM principals AND glue.amazonaws.com
#                          Glue needs to assume this role when running
#                          crawlers and ETL jobs — without this trust
#                          statement the crawler fails with a service error
# ─────────────────────────────────────────────────────────────────

# UNCHANGED — still used by ae, junior_de, readonly (roles 3, 4, 5)
data "aws_iam_policy_document" "assume_role_base" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

# UNCHANGED — admin role still requires MFA
data "aws_iam_policy_document" "assume_role_admin" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    condition {
      test     = "Bool"
      variable = "aws:MultiFactorAuthPresent"
      values   = ["true"]
    }
  }
}

# ── CHANGE 1 (new block, after line 103 in original) ─────────────
# NEW trust policy for senior_de only.
# Two principals:
#   1. AWS IAM root → lets you (and Airflow/EC2) assume this role
#   2. glue.amazonaws.com → lets the Glue SERVICE assume this role
#      when running crawlers and ETL jobs on your behalf.
#
# Why Glue needs this:
#   When you click "Run crawler" in the console (or Airflow triggers it),
#   it is the Glue SERVICE that assumes olist-senior-de-role to read S3
#   and write to the Data Catalog. If glue.amazonaws.com is not in the
#   trust policy, AWS rejects the AssumeRole call → "service error".
# ─────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "assume_role_senior_de" {
  # IAM principals (you, Airflow on EC2) can assume this role
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  # Glue service can assume this role for crawlers and ETL jobs
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}
# ── END CHANGE 1 ─────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────
# ROLE 1 — olist-admin-role
# UNCHANGED
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "admin" {
  name               = "${var.project_name}-admin-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_admin.json

  tags = { Role = "admin" }
}

resource "aws_iam_role_policy_attachment" "admin_full" {
  role       = aws_iam_role.admin.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# ─────────────────────────────────────────────────────────────────
# ROLE 2 — olist-senior-de-role
# ── CHANGE 2 (was line 156 in original) ──────────────────────────
# assume_role_policy now points to assume_role_senior_de
# (was assume_role_base — which did not include glue.amazonaws.com)
# Everything else in this role block is UNCHANGED.
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "senior_de" {
  name               = "${var.project_name}-senior-de-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_senior_de.json # ← CHANGED

  tags = { Role = "senior-de" }
}

data "aws_iam_policy_document" "senior_de_perms" {
  # Full S3 access on the project bucket only
  statement {
    sid     = "S3FullProjectBucket"
    effect  = "Allow"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.data_lake.arn,
      "${aws_s3_bucket.data_lake.arn}/*",
    ]
  }

  # Full Glue — create/run crawlers, ETL jobs, manage Data Catalog
  statement {
    sid       = "GlueFull"
    effect    = "Allow"
    actions   = ["glue:*"]
    resources = ["*"]
  }

  # Full Redshift — create schemas, run COPY, manage workgroups
  statement {
    sid       = "RedshiftFull"
    effect    = "Allow"
    actions   = ["redshift:*", "redshift-serverless:*", "redshift-data:*"]
    resources = ["*"]
  }

  # Lambda invoke only — senior DE triggers functions but does not manage them
  statement {
    sid       = "LambdaInvoke"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-*"]
  }

  # CloudWatch — write logs, create alarms, describe metrics
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:GetMetricData",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "senior_de" {
  name   = "${var.project_name}-senior-de-policy"
  role   = aws_iam_role.senior_de.id
  policy = data.aws_iam_policy_document.senior_de_perms.json
}

# ─────────────────────────────────────────────────────────────────
# ROLE 3 — olist-ae-role
# UNCHANGED — still uses assume_role_base (no Glue trust needed)
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "ae" {
  name               = "${var.project_name}-ae-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json

  tags = { Role = "ae" }
}

data "aws_iam_policy_document" "ae_perms" {
  statement {
    sid    = "RedshiftConnect"
    effect = "Allow"
    actions = [
      "redshift:GetClusterCredentials",
      "redshift-serverless:GetCredentials",
      "redshift-data:ExecuteStatement",
      "redshift-data:DescribeStatement",
      "redshift-data:GetStatementResult",
      "redshift-data:ListDatabases",
      "redshift-data:ListSchemas",
      "redshift-data:ListTables",
    ]
    resources = ["*"]
  }

  statement {
    sid     = "S3ReadProcessed"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.data_lake.arn,
      "${aws_s3_bucket.data_lake.arn}/dev/processed/*",
      "${aws_s3_bucket.data_lake.arn}/prod/processed/*",
    ]
  }
}

resource "aws_iam_role_policy" "ae" {
  name   = "${var.project_name}-ae-policy"
  role   = aws_iam_role.ae.id
  policy = data.aws_iam_policy_document.ae_perms.json
}

# ─────────────────────────────────────────────────────────────────
# ROLE 4 — olist-junior-de-role
# UNCHANGED — still uses assume_role_base
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "junior_de" {
  name               = "${var.project_name}-junior-de-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json

  tags = { Role = "junior-de" }
}

data "aws_iam_policy_document" "junior_de_perms" {
  statement {
    sid     = "S3ReadDev"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.data_lake.arn,
      "${aws_s3_bucket.data_lake.arn}/dev/*",
    ]
  }

  statement {
    sid    = "GlueReadOnly"
    effect = "Allow"
    actions = [
      "glue:GetJob",
      "glue:GetJobs",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:GetCrawler",
      "glue:GetCrawlers",
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartition",
      "glue:GetPartitions",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "RedshiftReadRaw"
    effect = "Allow"
    actions = [
      "redshift-serverless:GetCredentials",
      "redshift-data:ExecuteStatement",
      "redshift-data:DescribeStatement",
      "redshift-data:GetStatementResult",
      "redshift-data:ListDatabases",
      "redshift-data:ListSchemas",
      "redshift-data:ListTables",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "junior_de" {
  name   = "${var.project_name}-junior-de-policy"
  role   = aws_iam_role.junior_de.id
  policy = data.aws_iam_policy_document.junior_de_perms.json
}

# ─────────────────────────────────────────────────────────────────
# ROLE 5 — olist-readonly-role
# UNCHANGED — still uses assume_role_base
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "readonly" {
  name               = "${var.project_name}-readonly-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json

  tags = { Role = "readonly" }
}

data "aws_iam_policy_document" "readonly_perms" {
  statement {
    sid    = "RedshiftReadAnalytics"
    effect = "Allow"
    actions = [
      "redshift-serverless:GetCredentials",
      "redshift-data:ExecuteStatement",
      "redshift-data:DescribeStatement",
      "redshift-data:GetStatementResult",
      "redshift-data:ListDatabases",
      "redshift-data:ListSchemas",
      "redshift-data:ListTables",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "readonly" {
  name   = "${var.project_name}-readonly-policy"
  role   = aws_iam_role.readonly.id
  policy = data.aws_iam_policy_document.readonly_perms.json
}

# ─────────────────────────────────────────────────────────────────
# GLUE DATA CATALOG DATABASE
# ── CHANGE 3 (new resource, added at end of file) ────────────────
# Creates the "olist_dev_raw" metadata database in the Glue Data Catalog.
# This is NOT a Redshift database — it is a namespace inside Glue where
# the crawler registers table schemas discovered from S3.
#
# Before this change: you had to create it manually in the console
# (Step 2 of Feature 1.4 → "Target database: create new → olist_dev_raw").
# After this change: terraform apply creates it automatically.
# ─────────────────────────────────────────────────────────────────
resource "aws_glue_catalog_database" "dev_raw" {
  name        = "olist_dev_raw"
  description = "Glue Data Catalog database for raw Olist CSVs — schema metadata only, no data stored here"
}

# ─────────────────────────────────────────────────────────────────
# GLUE CRAWLER
# ── CHANGE 4 (new resource, added at end of file) ────────────────
# Crawls s3://<bucket>/dev/raw/, infers schemas from the 9 Olist CSVs,
# and registers them as tables in olist_dev_raw above.
#
# role = senior_de — the crawler assumes olist-senior-de-role at runtime.
#   This works now because CHANGE 1 added glue.amazonaws.com to that
#   role's trust policy. Before CHANGE 1, this would produce a service error.
#
# schedule is omitted → on-demand only. Run it from the console or via
# Airflow's GlueCrawlerOperator at the start of the DAG.
#
# configuration JSON tells the crawler:
#   - Version 1.0 of the config schema
#   - CrawlerOutput: set tables to MergeNewColumns mode so re-running
#     the crawler adds any new columns without deleting existing ones.
#     This prevents accidental schema wipes if a CSV is re-uploaded.
# ─────────────────────────────────────────────────────────────────
resource "aws_glue_crawler" "dev_raw" {
  name          = "${var.project_name}-dev-raw-crawler"
  database_name = aws_glue_catalog_database.dev_raw.name
  role          = aws_iam_role.senior_de.arn
  description   = "Crawls dev/raw/ CSVs and registers schemas in the Glue Data Catalog"

  s3_target {
    path = "s3://${var.bucket_name}/dev/raw/"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Tables = { AddOrUpdateBehavior = "MergeNewColumns" }
    }
  })

  tags = {
    Role = "senior-de"
  }
}
