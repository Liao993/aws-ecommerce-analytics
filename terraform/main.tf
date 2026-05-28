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
# NOTE: aws_vpc / aws_subnets / aws_security_group removed.
#       Those were needed for the Glue connection VPC routing, which
#       we no longer use. Redshift Serverless is publicly accessible,
#       so Glue reaches it directly over JDBC. No VPC config needed.
# ─────────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

# ─────────────────────────────────────────────────────────────────
# S3 — Data Lake Bucket
# ─────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "data_lake" {
  bucket = var.bucket_name
  force_destroy = true
  tags   = { Name = var.bucket_name }

}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket                  = aws_s3_bucket.data_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration { status = "Enabled" }
}

locals {
  s3_prefixes = [
    "dev/raw/",
    "dev/processed/",
    "dev/analytics/",
    "dev/glue-scripts/",
    "dev/tmp/",
    "prod/raw/",
    "prod/processed/",
    "prod/analytics/",
    "prod/glue-scripts/",
  ]
}

resource "aws_s3_object" "prefixes" {
  for_each = toset(local.s3_prefixes)
  bucket   = aws_s3_bucket.data_lake.id
  key      = each.value
  content  = ""
}

# ─────────────────────────────────────────────────────────────────
# IAM — Trust Policies
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
  # henry-dev (and any IAM principal in this account) can assume this role
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
  # glue.amazonaws.com assumes this role when running ETL jobs.
  # This is what gives the Glue job its permissions (S3, Redshift, etc).
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
# IAM — Redshift S3 Access Role
# Attached to the Redshift Serverless namespace so the COPY command
# can read staged Parquet files from dev/tmp/ during Glue loads.
# Without this, COPY silently loads 0 rows.
# ─────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "assume_role_redshift" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "redshift_s3" {
  name               = "${var.project_name}-redshift-s3-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_redshift.json
  tags               = { Role = "redshift-s3" }
}

data "aws_iam_policy_document" "redshift_s3_perms" {
  statement {
    sid    = "S3ReadTmpAndProcessed"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      aws_s3_bucket.data_lake.arn,
      "${aws_s3_bucket.data_lake.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "redshift_s3" {
  name   = "${var.project_name}-redshift-s3-policy"
  role   = aws_iam_role.redshift_s3.id
  policy = data.aws_iam_policy_document.redshift_s3_perms.json
}
# ─────────────────────────────────────────────────────────────────
# IAM — Role 1: Admin
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "admin" {
  name               = "${var.project_name}-admin-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_admin.json
  tags               = { Role = "admin" }
}

resource "aws_iam_role_policy_attachment" "admin_full" {
  role       = aws_iam_role.admin.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# ─────────────────────────────────────────────────────────────────
# IAM — Role 2: Senior DE
# Permissions the Glue job runs with (S3 + Glue + Redshift + CW)
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "senior_de" {
  name               = "${var.project_name}-senior-de-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_senior_de.json
  tags               = { Role = "senior-de" }
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
    sid     = "RedshiftFull"
    effect  = "Allow"
    actions = ["redshift:*", "redshift-serverless:*", "redshift-data:*"]
    resources = ["*"]
  }

  statement {
    sid     = "LambdaInvoke"
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-*"
    ]
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
      "cloudwatch:PutMetricData",
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
# IAM — Role 3: AE
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "ae" {
  name               = "${var.project_name}-ae-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json
  tags               = { Role = "ae" }
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
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "junior_de" {
  name               = "${var.project_name}-junior-de-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json
  tags               = { Role = "junior-de" }
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
      "glue:GetJob", "glue:GetJobs", "glue:GetJobRun", "glue:GetJobRuns",
      "glue:GetCrawler", "glue:GetCrawlers",
      "glue:GetDatabase", "glue:GetDatabases",
      "glue:GetTable", "glue:GetTables",
      "glue:GetPartition", "glue:GetPartitions",
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
# IAM — Role 5: Read-only
# ─────────────────────────────────────────────────────────────────

resource "aws_iam_role" "readonly" {
  name               = "${var.project_name}-readonly-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role_base.json
  tags               = { Role = "readonly" }
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
# ─────────────────────────────────────────────────────────────────

resource "aws_glue_catalog_database" "dev_raw" {
  name        = "olist_dev_raw"
  description = "Schema metadata for raw Olist CSVs in dev/raw/"
}
resource "aws_glue_catalog_database" "dev_processed" {
  name        = "olist_dev_processed"
  description = "Schema metadata for processed Olist Parquet in dev/processed/"
}

# ─────────────────────────────────────────────────────────────────
# Glue — Crawler
# ─────────────────────────────────────────────────────────────────

resource "aws_glue_crawler" "dev_raw" {
  name          = "${var.project_name}-dev-raw-crawler"
  database_name = aws_glue_catalog_database.dev_raw.name
  role          = aws_iam_role.senior_de.arn
  description   = "Crawls dev/raw/ CSVs and registers schemas in the Glue Data Catalog"

  # One s3_target per CSV file — guarantees one catalog table per file.
  # This replaces the single broad s3_target + CombineCompatibleSchemas,
  # which was merging all 9 CSVs into one 38-column table.
  s3_target { path = "s3://${var.bucket_name}/dev/raw/olist_orders_dataset.csv" }
  s3_target { path = "s3://${var.bucket_name}/dev/raw/olist_customers_dataset.csv" }
  s3_target { path = "s3://${var.bucket_name}/dev/raw/olist_order_items_dataset.csv" }
  s3_target { path = "s3://${var.bucket_name}/dev/raw/olist_order_payments_dataset.csv" }
  s3_target { path = "s3://${var.bucket_name}/dev/raw/olist_order_reviews_dataset.csv" }
  s3_target { path = "s3://${var.bucket_name}/dev/raw/olist_products_dataset.csv" }
  s3_target { path = "s3://${var.bucket_name}/dev/raw/olist_sellers_dataset.csv" }
  s3_target { path = "s3://${var.bucket_name}/dev/raw/olist_geolocation_dataset.csv" }
  s3_target { path = "s3://${var.bucket_name}/dev/raw/product_category_name_translation.csv" }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Tables = { AddOrUpdateBehavior = "MergeNewColumns" }
    }
  })
  # Tell the classifier to treat row 1 as a header
  classifiers = [aws_glue_classifier.csv_header.name]
  tags = { Role = "senior-de" }
}
resource "aws_glue_classifier" "csv_header" {
  name = "${var.project_name}-csv-classifier"

  csv_classifier {
    contains_header = "PRESENT"
    delimiter       = ","
    quote_symbol    = "\""
  }
}

# ─────────────────────────────────────────────────────────────────
# Glue — ETL Job: csv_to_parquet (Feature 1.4)
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
  timeout           = 10


  tags = { Role = "senior-de" }
}

# ─────────────────────────────────────────────────────────────────
# Glue — ETL Job: load_to_redshift (Feature 1.5)
#
# How auth works end-to-end:
#   1. henry-dev clicks "Run" in the Glue console
#   2. Glue calls sts:AssumeRole on olist-senior-de-role
#      (allowed because glue.amazonaws.com is a trusted principal)
#   3. The job now runs AS senior-de-role — it has S3 full access
#      (to read Parquet from dev/processed/ and write to dev/tmp/)
#   4. writers.py opens a JDBC connection to Redshift using
#      --REDSHIFT_USER (admin) and --REDSHIFT_PASSWORD
#      This is the Redshift DB login — completely separate from IAM
#   5. Glue issues a COPY command, Redshift reads from dev/tmp/ in S3
#
# No Glue connection object needed — Redshift is publicly accessible.
# ─────────────────────────────────────────────────────────────────


resource "aws_glue_job" "load_to_redshift" {
  name        = "${var.project_name}-load-to-redshift"
  role_arn    = aws_iam_role.senior_de.arn
  description = "Loads olist_orders Parquet from S3 into Redshift dev_raw schema"
  command {
    name            = "glueetl"
    script_location = "s3://${var.bucket_name}/dev/glue-scripts/load_to_redshift/main.py"
    python_version  = "3"
  }

  default_arguments = {
    "--extra-py-files" = join(",", [
      "s3://${var.bucket_name}/dev/glue-scripts/load_to_redshift/config.py",
      "s3://${var.bucket_name}/dev/glue-scripts/load_to_redshift/readers.py",
       "s3://${var.bucket_name}/dev/glue-scripts/load_to_redshift/transformers.py",
      "s3://${var.bucket_name}/dev/glue-scripts/load_to_redshift/writers.py",
      "s3://${var.bucket_name}/dev/glue-scripts/load_to_redshift/validators.py",
    ])

    "--REDSHIFT_URL"      = "jdbc:redshift://olist-workgroup.${data.aws_caller_identity.current.account_id}.ca-central-1.redshift-serverless.amazonaws.com:5439/dev"
    "--REDSHIFT_USER"     = "admin"
    "--REDSHIFT_PASSWORD" = var.redshift_password
    "--REDSHIFT_TMP_DIR"  = "s3://${var.bucket_name}/dev/tmp/"
    "--REDSHIFT_S3_ROLE_ARN" = aws_iam_role.redshift_s3.arn  
    
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--enable-glue-datacatalog"          = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--execution-class"                  = "FLEX" 
  }

  glue_version      = "4.0"
  number_of_workers = 2
  worker_type       = "G.1X"
  timeout           = 30

  tags = { Role = "senior-de" }
}
