"""
## Sales Transactions Daily Pipeline

**Workload**: `sales_transactions`
**Schedule**: Daily at 06:00 UTC (`0 6 * * *`)
**Owner**: data-engineering-team

### Pipeline Stages

| Stage     | Tasks                                      | Description                                       |
|-----------|--------------------------------------------|---------------------------------------------------|
| Extract   | sensor_s3_source, ingest_to_bronze         | Wait for raw file, copy to Bronze as Parquet       |
| Transform | bronze_to_silver, quality_check_silver     | Clean/mask PII, validate at 80% quality threshold  |
| Curate    | silver_to_gold, quality_check_gold         | Aggregate to Gold, validate at 95% quality threshold|
| Catalog   | update_catalog, update_semantic_metadata   | Register in Glue Catalog, update SageMaker metadata|

### Retry Policy
- 3 retries with exponential backoff (base 300s)
- SLA: 60 minutes for critical-path tasks
- Failure alerts via SNS

### Data Flow
```
S3 Raw CSV -> Bronze (Parquet) -> Silver (cleaned) -> Gold (aggregated) -> Catalog
```
"""

from datetime import datetime, timedelta
import json
import logging
import os
import subprocess
import sys

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

# Production alternative:
# from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
# from airflow.providers.amazon.aws.operators.glue import GlueJobOperator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from Airflow Variables (NEVER hardcode)
# ---------------------------------------------------------------------------
WORKLOAD_NAME = "sales_transactions"

# All infrastructure references come from Airflow Variables
S3_RAW_BUCKET = Variable.get("s3_raw_bucket", default_var="data-lake-raw")
S3_RAW_PREFIX = Variable.get(
    "s3_raw_prefix_sales", default_var="sales/transactions/"
)
S3_BRONZE_BUCKET = Variable.get("s3_bronze_bucket", default_var="data-lake-bronze")
S3_BRONZE_PREFIX = Variable.get(
    "s3_bronze_prefix_sales", default_var="sales/transactions/"
)
QUALITY_THRESHOLD_SILVER = float(
    Variable.get("quality_threshold_silver_sales", default_var="0.80")
)
QUALITY_THRESHOLD_GOLD = float(
    Variable.get("quality_threshold_gold_sales", default_var="0.95")
)
SNS_TOPIC_ARN = Variable.get(
    "sns_alert_topic_arn",
    default_var="arn:aws:sns:us-east-1:ACCOUNT_ID:data-pipeline-alerts",
)
BASE_PATH = Variable.get(
    "base_path",
    default_var="/path/to/claude-data-operations",
)
WORKLOAD_PATH = os.path.join(BASE_PATH, "workloads", WORKLOAD_NAME)
SCRIPTS_PATH = os.path.join(WORKLOAD_PATH, "scripts")


# ---------------------------------------------------------------------------
# Callback: alert on failure
# ---------------------------------------------------------------------------
def alert_on_failure(context):
    """Send an alert when a task fails.

    In production this would publish to SNS / Slack / PagerDuty.
    For local development it logs the failure details.
    """
    task_instance = context.get("task_instance")
    dag_id = context.get("dag").dag_id
    task_id = task_instance.task_id if task_instance else "unknown"
    execution_date = context.get("execution_date", "unknown")
    exception = context.get("exception", "")

    message = (
        f"ALERT: Task failed | dag={dag_id} | task={task_id} | "
        f"execution_date={execution_date} | error={exception}"
    )
    logger.error(message)

    # Production: publish to SNS
    # import boto3
    # sns = boto3.client("sns")
    # sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=f"Pipeline Failure: {dag_id}", Message=message)


# ---------------------------------------------------------------------------
# Task callables — delegate to existing scripts, no inline computation
# ---------------------------------------------------------------------------
def sensor_s3_source_callable(**kwargs):
    """Wait for the raw source file to arrive in S3.

    In production, replace this PythonOperator with:
        S3KeySensor(
            task_id='sensor_s3_source',
            bucket_name=S3_RAW_BUCKET,
            bucket_key=f'{S3_RAW_PREFIX}sales_transactions_*.csv',
            aws_conn_id='aws_default',
            poke_interval=60,
            timeout=1800,
        )

    For local execution, we verify the sample data file exists.
    """
    sample_data_path = os.path.join(BASE_PATH, "sample_data", "sales_transactions.csv")
    if not os.path.isfile(sample_data_path):
        raise FileNotFoundError(
            f"Source file not found: {sample_data_path}. "
            "In production this would be an S3KeySensor."
        )
    logger.info("Source file detected: %s", sample_data_path)
    return sample_data_path


def ingest_to_bronze_callable(**kwargs):
    """Copy raw data to Bronze zone (as Parquet in production).

    In production, replace with:
        GlueJobOperator or S3CopyObjectOperator
        converting CSV to Parquet with partitioning.

    For local execution, this is a pass-through — Bronze is the sample_data/ folder.
    """
    sample_data_path = os.path.join(BASE_PATH, "sample_data", "sales_transactions.csv")
    logger.info(
        "Ingesting raw data to Bronze zone. Source: %s", sample_data_path
    )
    # In production: convert to Parquet, add ingestion metadata columns
    # (_ingested_at, _source_file, _batch_id), write to S3 Bronze bucket.
    return {"bronze_path": sample_data_path, "row_count": "pending"}


def bronze_to_silver_callable(**kwargs):
    """Run Bronze-to-Silver transformation via existing script.

    Calls: scripts/transform/bronze_to_silver.py
    """
    script_path = os.path.join(SCRIPTS_PATH, "transform", "bronze_to_silver.py")
    logger.info("Running Bronze-to-Silver transform: %s", script_path)

    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        cwd=WORKLOAD_PATH,
        timeout=600,
    )
    if result.returncode != 0:
        logger.error("bronze_to_silver STDERR: %s", result.stderr)
        raise RuntimeError(
            f"Bronze-to-Silver transformation failed (exit code {result.returncode}): "
            f"{result.stderr}"
        )
    logger.info("bronze_to_silver STDOUT: %s", result.stdout)
    return {"status": "success", "output": result.stdout[-500:] if result.stdout else ""}


def quality_check_silver_callable(**kwargs):
    """Run quality checks on Silver zone data.

    Calls: scripts/quality/run_quality_checks.py with the silver CSV
    and the Bronze-to-Silver threshold (0.80).
    """
    script_path = os.path.join(SCRIPTS_PATH, "quality", "run_quality_checks.py")
    silver_csv = os.path.join(WORKLOAD_PATH, "data", "silver", "sales_transactions_clean.csv")

    logger.info(
        "Running quality checks on Silver data (threshold=%.2f): %s",
        QUALITY_THRESHOLD_SILVER,
        silver_csv,
    )

    result = subprocess.run(
        [
            sys.executable,
            script_path,
            silver_csv,
            "--threshold",
            str(QUALITY_THRESHOLD_SILVER),
        ],
        capture_output=True,
        text=True,
        cwd=WORKLOAD_PATH,
        timeout=600,
    )
    logger.info("quality_check_silver STDOUT: %s", result.stdout)
    if result.returncode != 0:
        logger.error("quality_check_silver STDERR: %s", result.stderr)
        raise RuntimeError(
            f"Silver quality check failed (exit code {result.returncode}): "
            f"{result.stderr}\n{result.stdout}"
        )
    return {"status": "passed", "threshold": QUALITY_THRESHOLD_SILVER}


def silver_to_gold_callable(**kwargs):
    """Run Silver-to-Gold aggregation via existing script.

    Calls: scripts/transform/silver_to_gold.py
    """
    script_path = os.path.join(SCRIPTS_PATH, "transform", "silver_to_gold.py")
    logger.info("Running Silver-to-Gold aggregation: %s", script_path)

    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        cwd=WORKLOAD_PATH,
        timeout=600,
    )
    if result.returncode != 0:
        logger.error("silver_to_gold STDERR: %s", result.stderr)
        raise RuntimeError(
            f"Silver-to-Gold aggregation failed (exit code {result.returncode}): "
            f"{result.stderr}"
        )
    logger.info("silver_to_gold STDOUT: %s", result.stdout)
    return {"status": "success", "output": result.stdout[-500:] if result.stdout else ""}


def quality_check_gold_callable(**kwargs):
    """Run quality checks on Gold zone data.

    Calls: scripts/quality/run_quality_checks.py with the gold CSV
    and the Silver-to-Gold threshold (0.95).
    """
    script_path = os.path.join(SCRIPTS_PATH, "quality", "run_quality_checks.py")
    gold_csv = os.path.join(
        WORKLOAD_PATH, "data", "gold", "sales_summary_by_region_category.csv"
    )

    logger.info(
        "Running quality checks on Gold data (threshold=%.2f): %s",
        QUALITY_THRESHOLD_GOLD,
        gold_csv,
    )

    result = subprocess.run(
        [
            sys.executable,
            script_path,
            gold_csv,
            "--threshold",
            str(QUALITY_THRESHOLD_GOLD),
        ],
        capture_output=True,
        text=True,
        cwd=WORKLOAD_PATH,
        timeout=600,
    )
    logger.info("quality_check_gold STDOUT: %s", result.stdout)
    if result.returncode != 0:
        logger.error("quality_check_gold STDERR: %s", result.stderr)
        raise RuntimeError(
            f"Gold quality check failed (exit code {result.returncode}): "
            f"{result.stderr}\n{result.stdout}"
        )
    return {"status": "passed", "threshold": QUALITY_THRESHOLD_GOLD}


def update_catalog_callable(**kwargs):
    """Register or update AWS Glue Data Catalog entries for the Gold table.

    In production, replace with:
        GlueCrawlerOperator or a direct Glue API call to create/update
        the table in the 'gold' database.

    For local execution, this logs the catalog entry that would be created.
    """
    catalog_entry = {
        "database": "gold",
        "table": "sales_summary_by_region_category",
        "columns": [
            {"name": "region", "type": "string"},
            {"name": "product_category", "type": "string"},
            {"name": "total_revenue", "type": "double"},
            {"name": "avg_revenue", "type": "double"},
            {"name": "min_revenue", "type": "double"},
            {"name": "max_revenue", "type": "double"},
            {"name": "total_quantity", "type": "int"},
            {"name": "order_count", "type": "int"},
        ],
        "location": f"s3://{S3_BRONZE_BUCKET}/gold/sales/summary_by_region_category/",
        "format": "parquet",
        "partition_keys": [],
    }
    logger.info("Glue Catalog entry (would create/update): %s", json.dumps(catalog_entry, indent=2))

    # Production:
    # import boto3
    # glue = boto3.client("glue")
    # glue.create_table(...) or glue.update_table(...)
    return {"status": "catalog_updated", "table": catalog_entry["table"]}


def update_semantic_metadata_callable(**kwargs):
    """Update SageMaker Catalog custom metadata for the workload.

    In production, this would call the SageMaker Catalog API to
    register/update the dataset's semantic metadata (column descriptions,
    business roles, PII classifications, quality scores).

    For local execution, this reads semantic.yaml and logs the metadata
    that would be pushed.
    """
    import yaml

    semantic_path = os.path.join(WORKLOAD_PATH, "config", "semantic.yaml")
    logger.info("Reading semantic metadata: %s", semantic_path)

    with open(semantic_path, "r") as f:
        semantic = yaml.safe_load(f)

    dataset_name = semantic.get("dataset", {}).get("name", WORKLOAD_NAME)
    column_count = len(semantic.get("columns", []))
    pii_columns = semantic.get("pii_summary", {}).get("columns_with_pii", [])

    logger.info(
        "SageMaker Catalog metadata (would update): dataset=%s, columns=%d, pii_columns=%s",
        dataset_name,
        column_count,
        pii_columns,
    )

    # Production:
    # Call SageMaker Catalog API to create/update the dataset entry
    # with column-level metadata, tags, and lineage info.
    return {
        "status": "metadata_updated",
        "dataset": dataset_name,
        "column_count": column_count,
        "pii_columns": pii_columns,
    }


# ---------------------------------------------------------------------------
# Default args — applied to every task
# ---------------------------------------------------------------------------
default_args = {
    "owner": "data-engineering-team",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(seconds=300),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(seconds=3600),
    "execution_timeout": timedelta(minutes=30),
    "on_failure_callback": alert_on_failure,
}


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="sales_transactions_daily",
    default_args=default_args,
    description="Bronze -> Silver -> Gold pipeline for sales_transactions",
    schedule="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["sales", "data-onboarding", "daily"],
    doc_md=__doc__,
) as dag:

    # -----------------------------------------------------------------------
    # TaskGroup: extract
    # -----------------------------------------------------------------------
    with TaskGroup("extract") as extract_group:

        sensor_s3_source = PythonOperator(
            task_id="sensor_s3_source",
            python_callable=sensor_s3_source_callable,
            # Production: replace with S3KeySensor
            # S3KeySensor(
            #     task_id='sensor_s3_source',
            #     bucket_name=S3_RAW_BUCKET,
            #     bucket_key=f'{S3_RAW_PREFIX}sales_transactions_*.csv',
            #     aws_conn_id='aws_default',
            #     poke_interval=60,
            #     timeout=1800,
            # )
            sla=timedelta(minutes=15),
        )

        ingest_to_bronze = PythonOperator(
            task_id="ingest_to_bronze",
            python_callable=ingest_to_bronze_callable,
            # Production: replace with GlueJobOperator or S3CopyObjectOperator
        )

        sensor_s3_source >> ingest_to_bronze

    # -----------------------------------------------------------------------
    # TaskGroup: transform
    # -----------------------------------------------------------------------
    with TaskGroup("transform") as transform_group:

        bronze_to_silver = PythonOperator(
            task_id="bronze_to_silver",
            python_callable=bronze_to_silver_callable,
            sla=timedelta(minutes=20),
        )

        quality_check_silver = PythonOperator(
            task_id="quality_check_silver",
            python_callable=quality_check_silver_callable,
            trigger_rule="all_success",
            sla=timedelta(minutes=30),
        )

        bronze_to_silver >> quality_check_silver

    # -----------------------------------------------------------------------
    # TaskGroup: curate
    # -----------------------------------------------------------------------
    with TaskGroup("curate") as curate_group:

        silver_to_gold = PythonOperator(
            task_id="silver_to_gold",
            python_callable=silver_to_gold_callable,
            sla=timedelta(minutes=40),
        )

        quality_check_gold = PythonOperator(
            task_id="quality_check_gold",
            python_callable=quality_check_gold_callable,
            trigger_rule="all_success",
            sla=timedelta(minutes=50),
        )

        silver_to_gold >> quality_check_gold

    # -----------------------------------------------------------------------
    # TaskGroup: catalog
    # -----------------------------------------------------------------------
    with TaskGroup("catalog") as catalog_group:

        update_catalog = PythonOperator(
            task_id="update_catalog",
            python_callable=update_catalog_callable,
        )

        update_semantic_metadata = PythonOperator(
            task_id="update_semantic_metadata",
            python_callable=update_semantic_metadata_callable,
            sla=timedelta(minutes=55),
        )

        update_catalog >> update_semantic_metadata

    # -----------------------------------------------------------------------
    # TaskGroup dependencies: extract >> transform >> curate >> catalog
    # -----------------------------------------------------------------------
    extract_group >> transform_group >> curate_group >> catalog_group
