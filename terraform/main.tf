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
# Data Sources
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

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 has no real folders — zero-byte objects simulate the prefix
# structure so the console and Glue Crawlers see the expected layout.
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
# IAM — Trust Policies
#
# assume_role_base      shared by ae, junior_de, readonly
#                       IAM principals in this account only
#
# assume_role_admin     admin only, MFA required
#
# assume_role_senior_de senior_de only
#                       IAM principals + glue.amazonaws.com
#                       Glue must assume this role to run crawlers
#                       and ETL jobs — without it you get a service error
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

  # Glue service assumes this role when running crawlers and ETL jobs
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

# ─────────────────────────────────────────────────────────────────
# IAM — Role 1: Admin
# Full AdministratorAccess, MFA required to assume
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
# IAM — Role 2: Senior DE
# S3 full + Glue full + Redshift full + Lambda invoke + CloudWatch
# Trusted by glue.amazonaws.com so Glue can assume it for jobs
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "senior_de" {
  name               = "${var.project_name}-senior-de-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_senior_de.json

  tags = { Role = "senior-de" }
}

data "aws_iam_policy_document" "senior_de_perms" {
  statement {
    sid     = "S3FullProjectBucket"
    effect  = "Allow"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.data_lake.arn,
      "${aws_s3_bucket.data_lake.arn}/*",
    ]
  }

  statement {
    sid       = "GlueFull"
    effect    = "Allow"
    actions   = ["glue:*"]
    resources = ["*"]
  }

  statement {
    sid       = "RedshiftFull"
    effect    = "Allow"
    actions   = ["redshift:*", "redshift-serverless:*", "redshift-data:*"]
    resources = ["*"]
  }

  statement {
    sid       = "LambdaInvoke"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-*"]
  }

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
# IAM — Role 3: AE (Analytics Engineer / dbt)
# Redshift read/write on staging + intermediate + marts
# S3 read on processed/ only
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
# IAM — Role 4: Junior DE
# S3 read on dev/ only + Glue read-only + Redshift read on raw schema
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
# IAM — Role 5: Read-only (DA / Sales)
# Redshift read-only on analytics schema only
# Zero access to raw data or pipeline infrastructure
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
# Glue — Data Catalog Database
# Metadata namespace for raw Olist CSV schemas.
# NOT a Redshift database — no data is stored here,
# only schema definitions discovered by the crawler.
# ─────────────────────────────────────────────────────────────────

resource "aws_glue_catalog_database" "dev_raw" {
  name        = "olist_dev_raw"
  description = "Schema metadata for raw Olist CSVs in dev/raw/"
}

# ─────────────────────────────────────────────────────────────────
# Glue — Crawler
# Crawls dev/raw/, infers schemas from the 9 Olist CSVs, and
# registers them as tables in olist_dev_raw above.
# Schedule omitted — on-demand, triggered manually or by Airflow.
# MergeNewColumns prevents re-runs from wiping existing columns.
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

  tags = { Role = "senior-de" }
}

# ─────────────────────────────────────────────────────────────────
# Glue — ETL Job: csv_to_parquet (Feature 1.4)
#
# Reads all 9 raw CSV tables from the Data Catalog and writes them
# to dev/processed/ as Snappy-compressed Parquet. Date-partitioned
# tables (orders, reviews) get year/month folder structure for
# Athena partition pruning.
#
# extra-py-files: the four helper modules main.py imports at runtime.
# Glue adds these to the Python path so local imports resolve.
# Without this, Glue only sees main.py and throws ModuleNotFoundError.
#
# G.1X / 2 workers: sufficient for 100K-row Olist dataset.
# Scale number_of_workers for larger datasets in future epics.
# ─────────────────────────────────────────────────────────────────

resource "aws_glue_job" "csv_to_parquet" {
  name        = "${var.project_name}-csv-to-parquet"
  role_arn    = aws_iam_role.senior_de.arn
  description = "Converts raw Olist CSVs to Snappy Parquet in dev/processed/"

  command {
    name            = "glueetl"
    script_location = "s3://${var.bucket_name}/dev/glue-scripts/csv_to_parquet/main.py"
    python_version  = "3"
  }

  default_arguments = {
    "--extra-py-files" = join(",", [
      "s3://${var.bucket_name}/dev/glue-scripts/csv_to_parquet/config.py",
      "s3://${var.bucket_name}/dev/glue-scripts/csv_to_parquet/readers.py",
      "s3://${var.bucket_name}/dev/glue-scripts/csv_to_parquet/transformers.py",
      "s3://${var.bucket_name}/dev/glue-scripts/csv_to_parquet/writers.py",
    ])
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--enable-glue-datacatalog"          = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
  }

  glue_version      = "4.0"
  number_of_workers = 2
  worker_type       = "G.1X"

  tags = { Role = "senior-de" }
}
