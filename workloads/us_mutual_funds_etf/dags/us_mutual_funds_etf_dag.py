"""
US Mutual Funds & ETF Data Pipeline
====================================

End-to-end Bronze→Silver→Gold pipeline for US mutual fund and ETF performance data.

Orchestrates 8 Glue ETL jobs and 2 quality check jobs through a medallion architecture:
- Bronze: Generate synthetic fund data (130 funds, 130 market records, 150 NAV records)
- Silver: Clean and validate (dedup, standardize, Iceberg tables)
- Gold: Model star schema (3 dimension tables + 1 fact table)

Quality gates at Silver (0.80 threshold) and Gold (0.95 threshold) block progression on failures.

Schedule: Monthly on 1st of month at 02:00 UTC
Author: Orchestration DAG Agent
Created: 2026-03-16
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.models import Variable
from airflow.operators.dummy import DummyOperator
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.utils.task_group import TaskGroup


# ============================================================================
# Configuration from Airflow Variables
# ============================================================================

S3_BUCKET = Variable.get("finsights_s3_bucket", default_var="your-datalake-bucket")
GLUE_ROLE = Variable.get("finsights_glue_role", default_var="GlueServiceRole")
AWS_REGION = Variable.get("aws_region", default_var="us-east-1")
GLUE_VERSION = Variable.get("glue_version", default_var="4.0")
WORKER_TYPE = Variable.get("glue_worker_type", default_var="G.1X")
SLACK_CONN_ID = Variable.get("slack_connection_id", default_var="slack_data_alerts")


# ============================================================================
# Failure Notification Callback
# ============================================================================

def notify_failure(context):
    """Send Slack notification on task failure"""
    from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

    task_instance = context.get('task_instance')
    dag_id = task_instance.dag_id
    task_id = task_instance.task_id
    execution_date = context.get('execution_date')
    log_url = task_instance.log_url

    slack_msg = f"""
:red_circle: *Airflow Task Failed*
*DAG*: {dag_id}
*Task*: {task_id}
*Execution Time*: {execution_date}
*Log*: {log_url}
    """.strip()

    try:
        SlackWebhookOperator(
            task_id="slack_alert",
            http_conn_id=SLACK_CONN_ID,
            message=slack_msg,
        ).execute(context=context)
    except Exception as e:
        # If Slack notification fails, log error but don't fail the callback
        print(f"Failed to send Slack notification: {e}")


def notify_sla_miss(dag, task_list, blocking_task_list, slas, blocking_tis):
    """Send Slack notification on SLA miss"""
    from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

    slack_msg = f"""
:warning: *Airflow SLA Missed*
*DAG*: {dag.dag_id}
*Tasks*: {', '.join([t.task_id for t in task_list])}
*Blocking Tasks*: {', '.join([t.task_id for t in blocking_task_list]) if blocking_task_list else 'None'}
    """.strip()

    try:
        SlackWebhookOperator(
            task_id="slack_sla_alert",
            http_conn_id=SLACK_CONN_ID,
            message=slack_msg,
        ).execute(context={})
    except Exception as e:
        print(f"Failed to send SLA Slack notification: {e}")


# ============================================================================
# DAG Definition
# ============================================================================

default_args = {
    "owner": "data_engineering",
    "depends_on_past": False,
    "email": ["data-eng@company.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "on_failure_callback": notify_failure,
}

dag = DAG(
    dag_id="us_mutual_funds_etf_pipeline",
    default_args=default_args,
    description="End-to-end Bronze→Silver→Gold pipeline for US Mutual Funds & ETF data",
    schedule_interval="0 2 1 * *",  # 1st of month, 02:00 UTC
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["finance", "iceberg", "medallion", "funds"],
    sla_miss_callback=notify_sla_miss,
    doc_md="""
# US Mutual Funds & ETF Data Pipeline

## Purpose
Generate and process synthetic US mutual fund and ETF performance data through a medallion architecture.

## Zones
- **Bronze**: Raw Parquet files with intentional quality issues (130 funds, 130 market records, 150 NAV records)
- **Silver**: Cleaned Iceberg tables with quality gates (dedup, validation, standardization)
- **Gold**: Star schema Iceberg tables for analytics (4 tables: 3 dims + 1 fact)

## Data Flow
1. Generate synthetic Bronze data (Glue job)
2. Clean and validate to Silver (3 parallel Glue jobs)
3. Run Silver quality checks (quality gate: 80% threshold)
4. Model into Gold star schema (4 parallel Glue jobs)
5. Run Gold quality checks (quality gate: 95% threshold)

## Quality Gates
- Silver: 0.80 score, 0 critical failures
- Gold: 0.95 score, 0 critical failures
- Failures block downstream tasks

## Iceberg Tables
All Silver and Gold tables use Apache Iceberg format version 2, registered in AWS Glue Data Catalog.

## Schedule
Runs monthly on 1st of the month at 02:00 UTC.

## Notifications
- Email on failure: data-eng@company.com
- Slack on SLA miss: #data-alerts channel

## Job Dependencies
```
bronze_data_generation
  ├─► silver_funds_clean (parallel)
  ├─► silver_market_data_clean (parallel)
  └─► silver_nav_clean
        ├─► quality_gate_silver
        ├─► gold_dim_fund (parallel after quality gate)
        ├─► gold_dim_category (parallel after quality gate)
        ├─► gold_dim_date (parallel after quality gate)
        └─► gold_fact_fund_performance
              └─► quality_gate_gold
```

## SLA Targets
- Bronze Zone: 30 minutes
- Silver Zone: 45 minutes
- Gold Zone: 60 minutes
- Total Pipeline: 2 hours

## Author
Orchestration DAG Agent

## Version
1.0 (2026-03-16)
    """,
)


# ============================================================================
# Helper Function: Create Glue Job Operator
# ============================================================================

def create_glue_job_operator(
    task_id: str,
    job_name: str,
    script_path: str,
    description: str,
    sla_minutes: int = None,
    num_workers: int = 2,
    timeout_minutes: int = 60,
    execution_timeout_minutes: int = 90,
):
    """
    Factory function to create GlueJobOperator with consistent configuration.

    Args:
        task_id: Airflow task ID
        job_name: AWS Glue job name
        script_path: S3 path to Glue script (relative to bucket/scripts/)
        description: Task description for documentation
        sla_minutes: SLA threshold in minutes (optional)
        num_workers: Number of Glue workers (default: 2)
        timeout_minutes: Glue job timeout in minutes (default: 60)
        execution_timeout_minutes: Airflow execution timeout (default: 90)

    Returns:
        GlueJobOperator instance
    """
    return GlueJobOperator(
        task_id=task_id,
        job_name=job_name,
        script_location=f"s3://{S3_BUCKET}/scripts/{script_path}",
        s3_bucket=S3_BUCKET,
        iam_role_name=GLUE_ROLE,
        region_name=AWS_REGION,
        create_job_kwargs={
            "GlueVersion": GLUE_VERSION,
            "WorkerType": WORKER_TYPE,
            "NumberOfWorkers": num_workers,
            "Timeout": timeout_minutes,
            "DefaultArguments": {
                "--enable-spark-ui": "true",
                "--spark-event-logs-path": f"s3://{S3_BUCKET}/logs/spark-events/",
                "--enable-job-insights": "true",
                "--enable-glue-datacatalog": "true",
                "--job-language": "python",
                "--TempDir": f"s3://{S3_BUCKET}/tmp/",
                "--enable-metrics": "true",
                "--enable-continuous-cloudwatch-log": "true",
                "--continuous-log-logGroup": "/aws-glue/jobs/us_mutual_funds_etf",
            },
        },
        execution_timeout=timedelta(minutes=execution_timeout_minutes),
        sla=timedelta(minutes=sla_minutes) if sla_minutes else None,
        doc_md=description,
    )


# ============================================================================
# DAG Tasks
# ============================================================================

with dag:
    # Entry point
    start = DummyOperator(
        task_id="start",
        doc_md="Pipeline entry point - marks start of data processing flow",
    )

    # ========================================================================
    # BRONZE ZONE: Generate Synthetic Data
    # ========================================================================

    with TaskGroup(
        group_id="bronze_zone",
        tooltip="Generate raw synthetic data with intentional quality issues"
    ) as bronze_group:

        generate_bronze = create_glue_job_operator(
            task_id="generate_bronze_data",
            job_name="bronze_data_generation",
            script_path="bronze/bronze_data_generation.py",
            description="""
Generate synthetic Bronze data for 130 funds with intentional quality issues:
- raw_funds: Fund master data (tickers, names, types, inception dates)
- raw_market_data: Market metrics (expense ratios, beta, Sharpe, ratings)
- raw_nav_prices: NAV prices and historical returns (1mo, 3mo, YTD, 1yr, 3yr, 5yr)

Intentional quality issues injected:
- 5% null fund names
- 3% invalid fund types
- 5% outlier beta values
- 2% future inception dates
- 10% missing expense ratios

Output: Parquet files in s3://your-datalake-bucket/bronze/
            """,
            sla_minutes=30,
            num_workers=2,
            timeout_minutes=30,
            execution_timeout_minutes=45,
        )

    # ========================================================================
    # SILVER ZONE: Clean and Validate
    # ========================================================================

    with TaskGroup(
        group_id="silver_zone",
        tooltip="Clean, deduplicate, and validate data into Iceberg tables"
    ) as silver_group:

        # Parallel cleaning jobs
        clean_funds = create_glue_job_operator(
            task_id="clean_funds",
            job_name="silver_funds_clean",
            script_path="silver/silver_funds_clean.py",
            description="""
Clean raw_funds Bronze data into funds_clean Silver Iceberg table:
- Deduplicate by fund_ticker (keep most recent)
- Standardize fund_type: ETFs → 'ETF', Mutual Funds → 'Mutual Fund'
- Handle null fund names: replace with 'Unknown Fund'
- Remove future inception dates
- Validate inception_date >= 1985-01-01

Output: finsights_silver.funds_clean (Iceberg, ~130 rows after dedup)
            """,
            sla_minutes=15,
            num_workers=2,
            timeout_minutes=20,
            execution_timeout_minutes=30,
        )

        clean_market = create_glue_job_operator(
            task_id="clean_market_data",
            job_name="silver_market_data_clean",
            script_path="silver/silver_market_data_clean.py",
            description="""
Clean raw_market_data Bronze data into market_data_clean Silver Iceberg table:
- Deduplicate by fund_ticker
- Clamp beta to [0.0, 3.0] range
- Clamp sharpe_ratio to [-2.0, 5.0] range
- Clamp expense_ratio_pct to [0.0, 3.0] range
- Clamp dividend_yield_pct to [0.0, 15.0] range
- Validate morningstar_rating in [1, 5] or NULL

Output: finsights_silver.market_data_clean (Iceberg, ~130 rows)
            """,
            sla_minutes=15,
            num_workers=2,
            timeout_minutes=20,
            execution_timeout_minutes=30,
        )

        clean_nav = create_glue_job_operator(
            task_id="clean_nav_prices",
            job_name="silver_nav_clean",
            script_path="silver/silver_nav_clean.py",
            description="""
Clean raw_nav_prices Bronze data into nav_clean Silver Iceberg table:
- Deduplicate by (fund_ticker, price_date)
- Remove rows where nav <= 0
- Clamp all return_*_pct columns to [-50, 100] range
- Partition by year(price_date)

Output: finsights_silver.nav_clean (Iceberg, ~150 rows, partitioned by year)
            """,
            sla_minutes=15,
            num_workers=2,
            timeout_minutes=20,
            execution_timeout_minutes=30,
        )

        # Silver quality gate
        quality_gate_silver = create_glue_job_operator(
            task_id="quality_gate_silver",
            job_name="quality_checks_silver",
            script_path="silver/quality_checks_silver.py",
            description="""
Run comprehensive quality checks on Silver zone tables:
- Completeness: NOT NULL checks on critical columns
- Accuracy: Range validations (expense ratio, beta, NAV)
- Validity: Enum checks (fund_type), date range checks (inception_date)
- Uniqueness: Primary key deduplication checks
- Referential Integrity: FK check (nav_clean.fund_ticker → funds_clean.fund_ticker)
- Statistical Outliers: Z-score detection (beta), IQR detection (AUM)
- Volume Anomalies: Row count vs baseline

Threshold: 0.80 overall score, 0 critical failures
Blocks downstream tasks if quality gate fails.

Output: Quality report JSON to s3://your-datalake-bucket/quality_reports/silver/
            """,
            sla_minutes=10,
            num_workers=2,
            timeout_minutes=15,
            execution_timeout_minutes=20,
        )

        # Define Silver zone dependencies
        [clean_funds, clean_market, clean_nav] >> quality_gate_silver

    # ========================================================================
    # GOLD ZONE: Star Schema Modeling
    # ========================================================================

    with TaskGroup(
        group_id="gold_zone",
        tooltip="Model data into star schema for analytics"
    ) as gold_group:

        # Parallel dimension builds
        build_dim_fund = create_glue_job_operator(
            task_id="build_dim_fund",
            job_name="gold_dim_fund",
            script_path="gold/gold_dim_fund.py",
            description="""
Build dim_fund dimension table from Silver tables:
- Join funds_clean + market_data_clean
- Select fund attributes: ticker, name, type, company, dates, categories
- Primary key: fund_ticker

Output: finsights_gold.dim_fund (Iceberg, ~130 rows)
            """,
            sla_minutes=15,
            num_workers=2,
            timeout_minutes=20,
            execution_timeout_minutes=30,
        )

        build_dim_category = create_glue_job_operator(
            task_id="build_dim_category",
            job_name="gold_dim_category",
            script_path="gold/gold_dim_category.py",
            description="""
Build dim_category dimension table with surrogate keys:
- Extract unique combinations of (fund_category, asset_class, morningstar_category, benchmark_index, geographic_focus)
- Generate surrogate category_key
- Calculate typical_expense_min and typical_expense_max per category

Output: finsights_gold.dim_category (Iceberg, ~20-30 rows)
            """,
            sla_minutes=15,
            num_workers=2,
            timeout_minutes=20,
            execution_timeout_minutes=30,
        )

        build_dim_date = create_glue_job_operator(
            task_id="build_dim_date",
            job_name="gold_dim_date",
            script_path="gold/gold_dim_date.py",
            description="""
Build dim_date time dimension table:
- Extract unique price_date values from nav_clean
- Generate date_key (YYYYMMDD format)
- Add time attributes: month, month_name, quarter, year

Output: finsights_gold.dim_date (Iceberg, ~5-10 rows depending on date range)
            """,
            sla_minutes=10,
            num_workers=2,
            timeout_minutes=15,
            execution_timeout_minutes=20,
        )

        # Fact table build (depends on all dimensions)
        build_fact = create_glue_job_operator(
            task_id="build_fact_fund_performance",
            job_name="gold_fact_fund_performance",
            script_path="gold/gold_fact_fund_performance.py",
            description="""
Build fact_fund_performance fact table with foreign keys:
- Join nav_clean + market_data_clean + dim_category (lookup category_key) + dim_date (lookup date_key)
- Generate surrogate fact_id
- Grain: (fund_ticker, price_date)
- Measures: nav, total_assets_millions, expense_ratio_pct, dividend_yield_pct, beta, sharpe_ratio, morningstar_rating, return_*_pct
- Foreign keys: fund_ticker, category_key, date_key
- Partition by year(price_date)

Output: finsights_gold.fact_fund_performance (Iceberg, ~150 rows, partitioned by year)
            """,
            sla_minutes=20,
            num_workers=3,
            timeout_minutes=30,
            execution_timeout_minutes=45,
        )

        # Gold quality gate
        quality_gate_gold = create_glue_job_operator(
            task_id="quality_gate_gold",
            job_name="quality_checks_gold",
            script_path="gold/quality_checks_gold.py",
            description="""
Run comprehensive quality checks on Gold zone star schema:
- Completeness: NOT NULL checks on all primary keys and critical FKs
- Uniqueness: Primary key deduplication (fund_ticker, category_key, date_key, fact_id)
- Referential Integrity: FK checks (fact → dim_fund, fact → dim_category, fact → dim_date)
- Accuracy: Range validations (NAV > 0, expense ratios, returns)
- Consistency: Cross-table checks (typical_expense_min <= typical_expense_max)
- Distribution Shift: Kolmogorov-Smirnov test on return_1yr_pct

Threshold: 0.95 overall score, 0 critical failures
Final quality gate before data is published.

Output: Quality report JSON to s3://your-datalake-bucket/quality_reports/gold/
            """,
            sla_minutes=10,
            num_workers=2,
            timeout_minutes=15,
            execution_timeout_minutes=20,
        )

        # Define Gold zone dependencies
        # All dimensions build in parallel, then fact builds, then quality check
        [build_dim_fund, build_dim_category, build_dim_date] >> build_fact >> quality_gate_gold

    # Exit point
    end = DummyOperator(
        task_id="end",
        doc_md="Pipeline completion - all quality gates passed, data is ready for consumption",
    )

    # ========================================================================
    # DAG Flow
    # ========================================================================

    start >> bronze_group >> silver_group >> gold_group >> end


# ============================================================================
# Documentation
# ============================================================================

# DAG-level documentation is already in doc_md above.
# Task-level documentation is in each operator's doc_md parameter.

# For debugging, you can run:
#   airflow dags test us_mutual_funds_etf_pipeline 2025-01-01

# To trigger manually:
#   airflow dags trigger us_mutual_funds_etf_pipeline
