# AWS E-Commerce Analytics Pipeline

End-to-end data engineering and analytics engineering project built on AWS using the Brazilian Olist e-commerce dataset. The goal is to show how I design, orchestrate, validate, model, and serve a production-style analytics pipeline from raw files to business-ready marts and dashboards.

![AWS architecture design](docs/architecture/aws_architecture_design.png)

## Hiring-manager summary

- **AWS data engineering:** S3 raw/processed zones, Glue Crawler, Glue ETL, Redshift Serverless, Terraform, and Docker-based local development.
- **Pipeline orchestration:** Airflow DAG with task factories, fan-out/fan-in quality checks, retries, callbacks, and clear dependency ordering.
- **Data quality:** Great Expectations checks before loading plus dbt tests after transformation.
- **Analytics engineering:** dbt staging, intermediate, marts, snapshots, seeds, macros, documentation, and source freshness checks.
- **Data modeling:** star-schema marts with explicit fact grains, surrogate keys, and Type 2 history for customers and sellers.
- **Business delivery:** Streamlit dashboard and SQL analyses for seller performance, delivery delays, payments, cohorts, and RFM segmentation.

## Tech stack

| Area | Tools |
|---|---|
| Cloud data platform | Amazon S3, AWS Glue, Glue Crawler, Redshift Serverless |
| Orchestration | Apache Airflow |
| Transformation | dbt Core, SQL |
| Data quality | Great Expectations, dbt tests |
| Infrastructure | Terraform, Docker Compose |
| Serving layer | Streamlit, Plotly |
| Language | Python, SQL |

## Pipeline flow

```text
Olist CSV files
  -> S3 raw zone
  -> Glue Crawler catalog
  -> Glue ETL CSV-to-Parquet job
  -> S3 processed zone
  -> Great Expectations quality checks
  -> Glue ETL load to Redshift
  -> dbt staging, intermediate, snapshots, and marts
  -> dbt tests and documentation
  -> Streamlit dashboard and SQL analyses
```

## Modeling highlights

The dbt project uses a three-layer architecture:

- `staging`: one model per source table for renaming, casting, timestamp standardization, and source cleanup.
- `intermediate`: reusable business logic for order metrics, delivery calculations, payment aggregation, and customer cohorts.
- `marts`: analyst-friendly tables for seller performance, delivery analysis, category performance, payment behavior, customer cohorts, and RFM segmentation.

Historical correctness is handled with dbt snapshots for customers and sellers, preserving changing location attributes instead of overwriting history.

More detail:

- [Star schema documentation](docs/architecture/star_schema.md)
- [OLTP source schema](docs/architecture/oltp_schema.md)
- [Data model decisions](docs/architecture/data_model_decisions.md)

## Airflow orchestration

The main DAG is [`airflow/dags/dag.py`](airflow/dags/dag.py). It coordinates AWS ingestion, quality checks, warehouse loading, dbt modeling, tests, and documentation.

![Airflow pipeline](docs/screenshots/airflow_dag_screenshot.png)

The quality checks run in parallel inside an Airflow `TaskGroup`, and the warehouse load waits for every validation task to pass.

## Dashboard evidence

- [Seller performance](docs/screenshots/tab1_seller_performance.png)
- [Delivery delays](docs/screenshots/tab2_delivery_delays.png)
- [Payment behavior](docs/screenshots/tab4_payment_behavior.png)
- [RFM segmentation](docs/screenshots/tab5_rfm_segmentation.png)

## Business questions answered

The analysis layer in [`dbt_project/analyses`](dbt_project/analyses) uses the modeled marts to answer questions such as:

- Which sellers generate revenue but create customer-experience risk?
- Which delivery corridors have long actual delivery times or high late rates?
- How strong is repeat purchase behavior by customer cohort?
- How does installment usage relate to basket size?
- Which categories combine high revenue, high volume, and poor reviews?

## Best files to review

```text
airflow/dags/dag.py           Orchestration flow and dependencies
glue_jobs/                    Glue ETL jobs for Parquet conversion and Redshift loading
great_expectations/           Quality checks and validation runner
dbt_project/models/           Staging, intermediate, and mart models
dbt_project/snapshots/        Historical customer and seller tracking
dbt_project/analyses/         Business analysis SQL
terraform/                    AWS infrastructure definitions
dashboards/                   Streamlit dashboard application
```

## Run locally

Prerequisites:

- Docker Desktop with Docker Compose
- AWS credentials configured through `.env` for AWS-backed services
- Redshift and S3 configuration for the full cloud path

Start the dashboard services:

```bash
docker compose build
docker compose up -d dbt gx streamlit
```

Start Airflow locally:

```bash
docker compose up airflow-init
docker compose up -d airflow-webserver airflow-scheduler
```

Dashboard: `http://localhost:8503`

Airflow: `http://localhost:8080`

Useful dbt commands: `dbt run`, `dbt test`, `dbt snapshot`, `dbt compile`

Do not commit `.env`, credentials, access keys, Terraform state, or raw data.

## Project scope

This is a portfolio project designed to demonstrate production-minded data engineering patterns on a manageable public dataset. The Olist dataset is historical, so freshness warnings are expected in local runs. In production, I would add CI/CD deployment controls, row-level reconciliation, observability dashboards, alert routing, and a formal metric layer.

## Data source

Dataset: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)

Used for educational and portfolio purposes. Please review the source terms before redistributing the data.
