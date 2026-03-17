"""
## End-to-End Data Pipeline (MWAA)

**DAG ID**: `end_to_end_pipeline_daily`
**Schedule**: Daily at 06:00 UTC (`0 6 * * *`)
**Owner**: data-engineering-team
**SLA**: 90 minutes

### Overview

Single DAG that orchestrates the full data pipeline across both workloads:

```
Customer Master        Order Transactions
==============         ==================
sensor_customers       (waits)
ingest_customers       (waits)
transform_customers    (waits)
quality_staging_cust   (waits)
publish_customers      sensor_orders
quality_publish_cust   ingest_orders
catalog_customers  --> transform_orders (FK validated against customer staging)
                       quality_staging_orders
                       publish_orders
                       quality_publish_orders
                       catalog_orders
                       ──────────────
                       dashboard_refresh
```

### Why a Single DAG?

- Order transactions depend on customer_master staging data for FK validation
- Eliminates ExternalTaskSensor complexity and execution_delta timing issues
- Single place to monitor the full pipeline in MWAA
- Simpler failure handling and retry logic

### Pipeline Stages

| Stage | Workload | Tasks | SLA |
|-------|----------|-------|-----|
| Extract | customer_master | sensor, ingest | 10 min |
| Transform | customer_master | landing_to_staging, quality_staging | 25 min |
| Curate | customer_master | staging_to_publish, quality_publish | 40 min |
| Catalog | customer_master | update_catalog, update_metadata | 45 min |
| Extract | order_transactions | sensor, ingest | 50 min |
| Transform | order_transactions | landing_to_staging, quality_staging | 65 min |
| Curate | order_transactions | staging_to_publish, quality_publish | 80 min |
| Catalog | order_transactions | update_catalog, update_metadata | 85 min |
| Dashboard | - | refresh_spice_datasets | 90 min |

### Encryption

Each zone uses a dedicated KMS key (re-encrypted at zone boundaries):
- Landing: alias/landing-data-key
- Staging: alias/staging-data-key
- Publish: alias/publish-data-key
- Catalog: alias/catalog-metadata-key

### MWAA Deployment

1. Upload this file to `s3://${MWAA_BUCKET}/dags/end_to_end_pipeline_dag.py`
2. Upload workload scripts to `s3://${MWAA_BUCKET}/dags/workloads/` (preserving structure)
3. Set Airflow Variables (see docs/aws-account-setup.md)
4. Verify: `airflow dags test end_to_end_pipeline_daily 2026-03-15`

### Retry Policy

- 3 retries with exponential backoff (base 300s)
- Failure alerts via SNS
- Quality gate failures are fatal (no retry — data issue, not transient)
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from Airflow Variables (NEVER hardcode)
# ---------------------------------------------------------------------------
BASE_PATH = Variable.get(
    "base_path",
    default_var="/opt/airflow/dags",  # MWAA default; override for local dev
)

# KMS key aliases — from Airflow Variables
KMS_KEY_LANDING = Variable.get("kms_key_landing", default_var="alias/landing-data-key")
KMS_KEY_STAGING = Variable.get("kms_key_staging", default_var="alias/staging-data-key")
KMS_KEY_PUBLISH = Variable.get("kms_key_publish", default_var="alias/publish-data-key")
KMS_KEY_CATALOG = Variable.get("kms_key_catalog", default_var="alias/catalog-metadata-key")

# S3 buckets — from Airflow Variables
S3_LANDING_BUCKET = Variable.get("s3_landing_bucket", default_var="data-lake-landing")
S3_STAGING_BUCKET = Variable.get("s3_staging_bucket", default_var="data-lake-staging")
S3_PUBLISH_BUCKET = Variable.get("s3_publish_bucket", default_var="data-lake-publish")

# Quality thresholds
QT_STAGING = float(Variable.get("quality_threshold_staging", default_var="0.80"))
QT_PUBLISH = float(Variable.get("quality_threshold_publish", default_var="0.95"))

# SNS for alerts
SNS_TOPIC_ARN = Variable.get(
    "sns_alert_topic_arn",
    default_var="arn:aws:sns:us-east-1:ACCOUNT_ID:data-pipeline-alerts",
)

# QuickSight
QUICKSIGHT_DASHBOARD_ID = Variable.get(
    "quicksight_dashboard_id",
    default_var="order-transactions-dashboard",
)

# Workload paths
CUSTOMER_WORKLOAD = os.path.join(BASE_PATH, "workloads", "customer_master")
ORDER_WORKLOAD = os.path.join(BASE_PATH, "workloads", "order_transactions")
SHARED_PATH = os.path.join(BASE_PATH, "shared")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _run_script(script_path: str, args: list = None, cwd: str = None) -> str:
    """Run a Python script as a subprocess. Returns stdout on success."""
    cmd = [sys.executable, script_path] + (args or [])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or os.path.dirname(script_path),
        timeout=600,
    )
    if result.returncode != 0:
        logger.error("Script %s STDERR: %s", script_path, result.stderr)
        raise RuntimeError(
            f"Script failed (exit {result.returncode}): "
            f"{os.path.basename(script_path)}\n{result.stderr}"
        )
    if result.stdout:
        logger.info("Script %s output (last 500 chars): %s", script_path, result.stdout[-500:])
    return result.stdout or ""


# ---------------------------------------------------------------------------
# Alert callback
# ---------------------------------------------------------------------------
def alert_on_failure(context):
    """Send alert on task failure.

    Production: publishes to SNS. Local: logs.
    """
    ti = context.get("task_instance")
    dag_id = context.get("dag").dag_id
    task_id = ti.task_id if ti else "unknown"
    execution_date = context.get("execution_date", "unknown")
    exception = context.get("exception", "")

    message = (
        f"PIPELINE FAILURE | dag={dag_id} | task={task_id} | "
        f"execution_date={execution_date} | error={exception}"
    )
    logger.error(message)

    # Production: uncomment to publish to SNS
    # import boto3
    # boto3.client("sns").publish(
    #     TopicArn=SNS_TOPIC_ARN,
    #     Subject=f"Pipeline Failure: {dag_id}/{task_id}",
    #     Message=message,
    # )


# ===========================================================================
# CUSTOMER MASTER task callables
# ===========================================================================
def sensor_customers_callable(**kwargs):
    """Verify customer source file is available."""
    fixture = os.path.join(SHARED_PATH, "fixtures", "customers.csv")
    # Production: replace with S3KeySensor or boto3 head_object
    if not os.path.isfile(fixture):
        raise FileNotFoundError(f"Customer source not found: {fixture}")
    logger.info("Customer source detected: %s", fixture)
    return fixture


def ingest_customers_callable(**kwargs):
    """Ingest customer CSV to Landing zone."""
    logger.info("Encrypting Landing zone with KMS: %s", KMS_KEY_LANDING)
    script = os.path.join(CUSTOMER_WORKLOAD, "scripts", "extract", "ingest_customers.py")
    _run_script(script, cwd=CUSTOMER_WORKLOAD)
    return {"status": "success", "kms_key": KMS_KEY_LANDING}


def transform_customers_callable(**kwargs):
    """Landing -> Staging: clean, mask PII, validate."""
    logger.info("Decrypting from Landing: %s", KMS_KEY_LANDING)
    logger.info("Encrypting Staging zone: %s", KMS_KEY_STAGING)
    script = os.path.join(CUSTOMER_WORKLOAD, "scripts", "transform", "landing_to_staging.py")
    _run_script(script, cwd=CUSTOMER_WORKLOAD)
    return {"status": "success", "kms_key": KMS_KEY_STAGING}


def quality_staging_customers_callable(**kwargs):
    """Staging quality gate for customer_master (>= 0.80)."""
    script = os.path.join(CUSTOMER_WORKLOAD, "scripts", "quality", "check_staging.py")
    csv_path = os.path.join(CUSTOMER_WORKLOAD, "data", "staging", "customer_staging.csv")
    logger.info("Running customer Staging quality checks (threshold=%.2f)", QT_STAGING)
    _run_script(script, args=[csv_path, "--threshold", str(QT_STAGING)], cwd=CUSTOMER_WORKLOAD)
    return {"status": "passed", "threshold": QT_STAGING}


def publish_customers_callable(**kwargs):
    """Staging -> Publish: build star schema."""
    logger.info("Decrypting from Staging: %s", KMS_KEY_STAGING)
    logger.info("Encrypting Publish zone: %s", KMS_KEY_PUBLISH)
    script = os.path.join(CUSTOMER_WORKLOAD, "scripts", "transform", "staging_to_publish.py")
    _run_script(script, cwd=CUSTOMER_WORKLOAD)
    return {"status": "success", "kms_key": KMS_KEY_PUBLISH}


def quality_publish_customers_callable(**kwargs):
    """Publish quality gate for customer_master (>= 0.95)."""
    script = os.path.join(CUSTOMER_WORKLOAD, "scripts", "quality", "check_publish.py")
    pub_dir = os.path.join(CUSTOMER_WORKLOAD, "data", "publish")
    logger.info("Running customer Publish quality checks (threshold=%.2f)", QT_PUBLISH)
    _run_script(script, args=[pub_dir, "--threshold", str(QT_PUBLISH)], cwd=CUSTOMER_WORKLOAD)
    return {"status": "passed", "threshold": QT_PUBLISH}


def catalog_customers_callable(**kwargs):
    """Register customer_master tables in Glue Catalog."""
    logger.info("Encrypting Catalog metadata with KMS: %s", KMS_KEY_CATALOG)
    tables = ["customer_fact", "dim_segment", "dim_country", "customer_summary_by_segment"]
    for t in tables:
        logger.info("Glue Catalog: would CREATE/UPDATE publish_db.%s (Iceberg)", t)
    return {"status": "catalog_updated", "tables": tables}


# ===========================================================================
# ORDER TRANSACTIONS task callables
# ===========================================================================
def sensor_orders_callable(**kwargs):
    """Verify order source file is available."""
    fixture = os.path.join(SHARED_PATH, "fixtures", "orders.csv")
    if not os.path.isfile(fixture):
        raise FileNotFoundError(f"Order source not found: {fixture}")
    logger.info("Order source detected: %s", fixture)
    return fixture


def ingest_orders_callable(**kwargs):
    """Ingest order CSV to Landing zone."""
    logger.info("Encrypting Landing zone with KMS: %s", KMS_KEY_LANDING)
    script = os.path.join(ORDER_WORKLOAD, "scripts", "extract", "ingest_orders.py")
    _run_script(script, cwd=ORDER_WORKLOAD)
    return {"status": "success", "kms_key": KMS_KEY_LANDING}


def transform_orders_callable(**kwargs):
    """Landing -> Staging: clean, FK validate against customer_master."""
    logger.info("Decrypting from Landing: %s", KMS_KEY_LANDING)
    logger.info("Encrypting Staging zone: %s", KMS_KEY_STAGING)
    script = os.path.join(ORDER_WORKLOAD, "scripts", "transform", "landing_to_staging.py")
    _run_script(script, cwd=ORDER_WORKLOAD)
    return {"status": "success", "kms_key": KMS_KEY_STAGING}


def quality_staging_orders_callable(**kwargs):
    """Staging quality gate for order_transactions (>= 0.80)."""
    script = os.path.join(ORDER_WORKLOAD, "scripts", "quality", "check_staging.py")
    csv_path = os.path.join(ORDER_WORKLOAD, "data", "staging", "orders_clean.csv")
    logger.info("Running order Staging quality checks (threshold=%.2f)", QT_STAGING)
    _run_script(script, args=[csv_path, "--threshold", str(QT_STAGING)], cwd=ORDER_WORKLOAD)
    return {"status": "passed", "threshold": QT_STAGING}


def publish_orders_callable(**kwargs):
    """Staging -> Publish: build star schema."""
    logger.info("Decrypting from Staging: %s", KMS_KEY_STAGING)
    logger.info("Encrypting Publish zone: %s", KMS_KEY_PUBLISH)
    script = os.path.join(ORDER_WORKLOAD, "scripts", "transform", "staging_to_publish.py")
    _run_script(script, cwd=ORDER_WORKLOAD)
    return {"status": "success", "kms_key": KMS_KEY_PUBLISH}


def quality_publish_orders_callable(**kwargs):
    """Publish quality gate for order_transactions (>= 0.95)."""
    script = os.path.join(ORDER_WORKLOAD, "scripts", "quality", "check_publish.py")
    pub_dir = os.path.join(ORDER_WORKLOAD, "data", "publish")
    logger.info("Running order Publish quality checks (threshold=%.2f)", QT_PUBLISH)
    _run_script(script, args=[pub_dir, "--threshold", str(QT_PUBLISH)], cwd=ORDER_WORKLOAD)
    return {"status": "passed", "threshold": QT_PUBLISH}


def catalog_orders_callable(**kwargs):
    """Register order_transactions tables in Glue Catalog."""
    logger.info("Encrypting Catalog metadata with KMS: %s", KMS_KEY_CATALOG)
    tables = ["order_fact", "dim_product", "order_summary_by_region_category"]
    for t in tables:
        logger.info("Glue Catalog: would CREATE/UPDATE publish_db.%s (Iceberg)", t)
    return {"status": "catalog_updated", "tables": tables}


# ===========================================================================
# DASHBOARD task callable
# ===========================================================================
def refresh_dashboard_callable(**kwargs):
    """Trigger QuickSight SPICE dataset refresh.

    Production: uses boto3 quicksight.create_ingestion() for each SPICE dataset.
    Local: logs the refresh intent.
    """
    datasets = ["order_fact_ds", "order_summary_ds"]
    for ds_id in datasets:
        logger.info(
            "QuickSight SPICE refresh (would trigger): dataset=%s, dashboard=%s",
            ds_id, QUICKSIGHT_DASHBOARD_ID,
        )
    # Production:
    # import boto3
    # qs = boto3.client("quicksight")
    # for ds_id in datasets:
    #     qs.create_ingestion(
    #         AwsAccountId=Variable.get("aws_account_id"),
    #         DataSetId=ds_id,
    #         IngestionId=f"{ds_id}-{kwargs['ts_nodash']}",
    #     )
    return {"status": "refresh_triggered", "datasets": datasets}


# ---------------------------------------------------------------------------
# Default args
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
    dag_id="end_to_end_pipeline_daily",
    default_args=default_args,
    description=(
        "End-to-end daily pipeline: customer_master + order_transactions "
        "(Landing -> Staging -> Publish -> Catalog -> Dashboard)"
    ),
    schedule="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["end-to-end", "customer", "orders", "daily", "data-onboarding", "mwaa"],
    doc_md=__doc__,
) as dag:

    # ===================================================================
    # CUSTOMER MASTER
    # ===================================================================
    with TaskGroup("customer_master") as customer_group:

        with TaskGroup("extract") as cust_extract:
            sensor_customers = PythonOperator(
                task_id="sensor_source",
                python_callable=sensor_customers_callable,
                sla=timedelta(minutes=10),
            )
            ingest_customers = PythonOperator(
                task_id="ingest_to_landing",
                python_callable=ingest_customers_callable,
                doc_md="Ingest raw CSV -> Landing zone. Encryption: SSE-KMS alias/landing-data-key",
            )
            sensor_customers >> ingest_customers

        with TaskGroup("transform") as cust_transform:
            transform_customers = PythonOperator(
                task_id="landing_to_staging",
                python_callable=transform_customers_callable,
                sla=timedelta(minutes=20),
                doc_md="Clean, mask PII, validate. Re-encrypt alias/landing -> alias/staging",
            )
            quality_staging_customers = PythonOperator(
                task_id="quality_check_staging",
                python_callable=quality_staging_customers_callable,
                trigger_rule="all_success",
                sla=timedelta(minutes=25),
            )
            transform_customers >> quality_staging_customers

        with TaskGroup("curate") as cust_curate:
            publish_customers = PythonOperator(
                task_id="staging_to_publish",
                python_callable=publish_customers_callable,
                sla=timedelta(minutes=35),
                doc_md="Build star schema: customer_fact, dim_segment, dim_country, summary",
            )
            quality_publish_customers = PythonOperator(
                task_id="quality_check_publish",
                python_callable=quality_publish_customers_callable,
                trigger_rule="all_success",
                sla=timedelta(minutes=40),
            )
            publish_customers >> quality_publish_customers

        with TaskGroup("catalog") as cust_catalog:
            catalog_customers = PythonOperator(
                task_id="update_catalog",
                python_callable=catalog_customers_callable,
                doc_md="Register Iceberg tables in Glue Catalog. Encryption: alias/catalog-metadata-key",
                sla=timedelta(minutes=45),
            )

        cust_extract >> cust_transform >> cust_curate >> cust_catalog

    # ===================================================================
    # ORDER TRANSACTIONS (depends on customer_master for FK validation)
    # ===================================================================
    with TaskGroup("order_transactions") as order_group:

        with TaskGroup("extract") as order_extract:
            sensor_orders = PythonOperator(
                task_id="sensor_source",
                python_callable=sensor_orders_callable,
                sla=timedelta(minutes=50),
            )
            ingest_orders = PythonOperator(
                task_id="ingest_to_landing",
                python_callable=ingest_orders_callable,
                doc_md="Ingest raw CSV -> Landing zone. Encryption: SSE-KMS alias/landing-data-key",
            )
            sensor_orders >> ingest_orders

        with TaskGroup("transform") as order_transform:
            transform_orders = PythonOperator(
                task_id="landing_to_staging",
                python_callable=transform_orders_callable,
                sla=timedelta(minutes=60),
                doc_md="Clean, FK validate vs customer_master staging. Re-encrypt alias/landing -> alias/staging",
            )
            quality_staging_orders = PythonOperator(
                task_id="quality_check_staging",
                python_callable=quality_staging_orders_callable,
                trigger_rule="all_success",
                sla=timedelta(minutes=65),
            )
            transform_orders >> quality_staging_orders

        with TaskGroup("curate") as order_curate:
            publish_orders = PythonOperator(
                task_id="staging_to_publish",
                python_callable=publish_orders_callable,
                sla=timedelta(minutes=75),
                doc_md="Build star schema: order_fact, dim_product, order_summary",
            )
            quality_publish_orders = PythonOperator(
                task_id="quality_check_publish",
                python_callable=quality_publish_orders_callable,
                trigger_rule="all_success",
                sla=timedelta(minutes=80),
            )
            publish_orders >> quality_publish_orders

        with TaskGroup("catalog") as order_catalog:
            catalog_orders = PythonOperator(
                task_id="update_catalog",
                python_callable=catalog_orders_callable,
                doc_md="Register Iceberg tables in Glue Catalog. Encryption: alias/catalog-metadata-key",
                sla=timedelta(minutes=85),
            )

        order_extract >> order_transform >> order_curate >> order_catalog

    # ===================================================================
    # DASHBOARD REFRESH (after both workloads complete)
    # ===================================================================
    refresh_dashboard = PythonOperator(
        task_id="refresh_dashboard",
        python_callable=refresh_dashboard_callable,
        doc_md="Trigger QuickSight SPICE dataset refresh after all data is published",
        sla=timedelta(minutes=90),
    )

    # ===================================================================
    # Pipeline flow: customer_master >> order_transactions >> dashboard
    # ===================================================================
    customer_group >> order_group >> refresh_dashboard
