# Terraform — Infrastructure as Code

Provisions all AWS infrastructure for the Olist Analytics Platform. Run once before any pipeline work begins.

## What this provisions

**S3 bucket (`olist-ecommerce-tara888`)** — the data lake. Stores raw CSVs, processed Parquet, analytics outputs,
and Glue scripts under `dev/` and `prod/` prefixes. Versioning enabled so raw source files are always replayable.

**S3 prefix placeholders** — eight zero-byte objects that simulate folder structure (`dev/raw/`, `dev/processed/`,
`prod/raw/`, etc.). S3 has no real folders; these make the layout visible in the console and to Glue Crawlers.

**Five IAM roles** — least-privilege access control simulating a real data team:

| Role | Who | What they can do |
|---|---|---|
| `olist-admin-role` | You (emergencies only) | Full access, MFA required |
| `olist-senior-de-role` | Pipeline / Airflow | S3 + Glue + Redshift + Lambda + CloudWatch |
| `olist-ae-role` | dbt / CI | Redshift staging + marts, S3 processed read |
| `olist-junior-de-role` | Observer | S3 dev read + Glue read + Redshift raw read |
| `olist-readonly-role` | Analysts / Streamlit | Redshift connect only |

## How to run

```bash
docker compose run terraform init     # download AWS provider — run once per machine
docker compose run terraform plan     # preview what will be created — nothing touches AWS
docker compose run terraform apply    # build it — copy role ARNs from output to docs/claude/aws_config.md
```

## Destroy

```bash
docker compose run terraform destroy  # removes all resources defined here
```

Run destroy at the end of Epic 7 after all portfolio screenshots are taken, to avoid AWS charges post-free-tier.
Do NOT run destroy mid-project — it will delete the S3 bucket and all data inside it.
