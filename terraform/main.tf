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
# IAM — Shared trust policy (allows role assumption by IAM users
# within this account). Each role gets the same trust document —
# what differs is the *permission* policies attached below.
# ─────────────────────────────────────────────────────────────────

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

# Admin trust policy — same base but with an MFA condition.
# Without MFA the AssumeRole call is denied even for admins.
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

# ─────────────────────────────────────────────────────────────────
# ROLE 1 — olist-admin-role
# Who:    You, the developer, during infrastructure work only
# Trust:  Any IAM principal in this account — BUT only if MFA is active
# Perms:  AdministratorAccess (AWS managed policy — full access)
# Why:    Root user is never used after day 1. This role is your
#         emergency hatch. MFA condition means a stolen key alone
#         cannot assume it.
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
# Who:    The pipeline builder — Glue jobs, Airflow on EC2, Lambda
# Trust:  IAM principals in this account (no MFA required for
#         automation — Airflow/Lambda can't prompt for MFA)
# Perms:  S3 full + Glue full + Redshift full + Lambda invoke +
#         CloudWatch logs (for DAG failure alarms)
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "senior_de" {
  name               = "${var.project_name}-senior-de-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json

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
# ROLE 3 — olist-ae-role  (Analytics Engineer / dbt)
# Who:    dbt running transformations in Redshift
# Trust:  IAM principals in this account (dbt runs in Docker/CI)
# Perms:  Redshift read/write on staging, intermediate, marts schemas
#         S3 read on processed/ (dbt may reference external stages)
#         No Glue, no Lambda, no raw schema access
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "ae" {
  name               = "${var.project_name}-ae-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json

  tags = { Role = "ae" }
}

data "aws_iam_policy_document" "ae_perms" {
  # Redshift — connect, run queries, manage tables in staging/intermediate/marts
  # Note: Redshift schema-level permissions are enforced inside the DB (via GRANT),
  # not via IAM. This IAM policy grants the ability to connect and use the API.
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

  # S3 read on processed/ — dbt may query external tables backed by S3 Parquet
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
# Who:    A junior who can inspect the pipeline but not modify it
# Trust:  IAM principals in this account
# Perms:  S3 read (dev prefix only) + Glue read (no create/delete)
#         + Redshift connect (raw schema — enforced in DB via GRANT)
#         Cannot write to S3, cannot modify Glue jobs, cannot touch prod
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "junior_de" {
  name               = "${var.project_name}-junior-de-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json

  tags = { Role = "junior-de" }
}

data "aws_iam_policy_document" "junior_de_perms" {
  # S3 read — dev prefix only; cannot see prod data
  statement {
    sid     = "S3ReadDev"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.data_lake.arn,
      "${aws_s3_bucket.data_lake.arn}/dev/*",
    ]
  }

  # Glue read-only — can inspect jobs and catalog, cannot run or modify
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

  # Redshift connect — raw schema access enforced via GRANT inside Redshift
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
# Who:    Data analysts, sales team, Streamlit dashboard queries
# Trust:  IAM principals in this account
# Perms:  Redshift connect only — analytics schema read enforced via
#         GRANT inside Redshift. Zero S3, zero Glue, zero Lambda.
#         Cannot see raw data, pipeline config, or prod infrastructure.
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "readonly" {
  name               = "${var.project_name}-readonly-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json

  tags = { Role = "readonly" }
}

data "aws_iam_policy_document" "readonly_perms" {
  # Redshift connect — analytics schema read enforced inside the DB
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
