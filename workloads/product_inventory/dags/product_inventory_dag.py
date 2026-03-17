"""
Product Inventory Pipeline DAG

Daily orchestration of product inventory data from Bronze → Silver → Gold zones.

Pipeline Stages:
1. Ingest: Validate source data availability
2. Transform: Bronze → Silver → Gold with schema enforcement
3. Quality: Run quality checks at Silver and Gold boundaries
4. Publish: Register in Glue Catalog and update semantic layer

Data Zones:
- Bronze: s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/bronze/product_inventory/
- Silver: s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/silver/product_inventory/
- Gold: s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/product_inventory/

Quality Gates:
- Silver: Score >= 0.80, no critical failures
- Gold: Score >= 0.95, no critical failures

Schedule: Daily at 6 AM UTC (0 6 * * *)
Owner: data-engineering
SLA: 1 hour per transform stage
"""

from datetime import datetime, timedelta
from pathlib import Path
import sys

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
from airflow.models import Variable

# DAG Configuration
DAG_ID = "product_inventory_pipeline"
SCHEDULE_INTERVAL = "0 6 * * *"
START_DATE = datetime(2026, 3, 1)
DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
}

# S3 Paths (from Airflow Variables with defaults for local testing)
S3_BRONZE = Variable.get(
    "product_inventory_bronze_path",
    default_var="s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/bronze/product_inventory/"
)
S3_SILVER = Variable.get(
    "product_inventory_silver_path",
    default_var="s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/silver/product_inventory/"
)
S3_GOLD = Variable.get(
    "product_inventory_gold_path",
    default_var="s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/product_inventory/"
)

# Script paths (absolute)
WORKLOAD_ROOT = Path("/path/to/claude-data-operations/workloads/product_inventory")
SCRIPTS_ROOT = WORKLOAD_ROOT / "scripts"


def failure_callback(context):
    """
    Send SNS alert on DAG failure.

    In production, this would call boto3.client('sns').publish()
    with the SNS topic ARN from Airflow Variables.
    """
    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    execution_date = context["execution_date"]
    exception = context.get("exception")

    print(f"FAILURE ALERT: DAG {dag_id} task {task_id} failed at {execution_date}")
    print(f"Exception: {exception}")

    # In production:
    # sns_topic_arn = Variable.get("sns_alert_topic_arn")
    # sns_client = boto3.client('sns')
    # sns_client.publish(
    #     TopicArn=sns_topic_arn,
    #     Subject=f"Airflow Alert: {dag_id} Failed",
    #     Message=f"Task {task_id} failed at {execution_date}\n\nError: {exception}"
    # )


# Task functions (call scripts in workloads/product_inventory/scripts/)
def validate_source(**context):
    """Check that source data exists in Bronze zone."""
    import importlib.util

    script_path = SCRIPTS_ROOT / "extract" / "validate_source.py"
    spec = importlib.util.spec_from_file_location("validate_source", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_source"] = module
    spec.loader.exec_module(module)

    module.validate_source(S3_BRONZE)


def bronze_to_silver(**context):
    """Transform Bronze → Silver with schema enforcement."""
    import importlib.util

    script_path = SCRIPTS_ROOT / "transform" / "bronze_to_silver.py"
    spec = importlib.util.spec_from_file_location("bronze_to_silver", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bronze_to_silver"] = module
    spec.loader.exec_module(module)

    module.bronze_to_silver(S3_BRONZE, S3_SILVER)


def run_silver_quality_checks(**context):
    """Run quality checks on Silver zone data."""
    import importlib.util

    script_path = SCRIPTS_ROOT / "quality" / "silver_quality_checks.py"
    spec = importlib.util.spec_from_file_location("silver_quality_checks", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["silver_quality_checks"] = module
    spec.loader.exec_module(module)

    result = module.run_silver_quality_checks(S3_SILVER)

    # Block promotion if quality gate fails
    if result["overall_score"] < 0.80:
        raise ValueError(f"Silver quality gate failed: score {result['overall_score']:.2f} < 0.80")
    if result["critical_failures"] > 0:
        raise ValueError(f"Silver quality gate failed: {result['critical_failures']} critical failures")

    return result


def silver_to_gold(**context):
    """Transform Silver → Gold (star schema)."""
    import importlib.util

    script_path = SCRIPTS_ROOT / "transform" / "silver_to_gold.py"
    spec = importlib.util.spec_from_file_location("silver_to_gold", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["silver_to_gold"] = module
    spec.loader.exec_module(module)

    module.silver_to_gold(S3_SILVER, S3_GOLD)


def run_gold_quality_checks(**context):
    """Run quality checks on Gold zone data."""
    import importlib.util

    script_path = SCRIPTS_ROOT / "quality" / "gold_quality_checks.py"
    spec = importlib.util.spec_from_file_location("gold_quality_checks", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gold_quality_checks"] = module
    spec.loader.exec_module(module)

    result = module.run_gold_quality_checks(S3_GOLD)

    # Block promotion if quality gate fails
    if result["overall_score"] < 0.95:
        raise ValueError(f"Gold quality gate failed: score {result['overall_score']:.2f} < 0.95")
    if result["critical_failures"] > 0:
        raise ValueError(f"Gold quality gate failed: {result['critical_failures']} critical failures")

    return result


def register_catalog(**context):
    """Register Gold tables in Glue Data Catalog."""
    import importlib.util

    script_path = SCRIPTS_ROOT / "load" / "register_catalog.py"
    spec = importlib.util.spec_from_file_location("register_catalog", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["register_catalog"] = module
    spec.loader.exec_module(module)

    module.register_catalog(S3_GOLD)


def update_semantic_layer(**context):
    """Update SageMaker Catalog with business metadata."""
    import importlib.util

    script_path = SCRIPTS_ROOT / "load" / "update_semantic_layer.py"
    spec = importlib.util.spec_from_file_location("update_semantic_layer", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["update_semantic_layer"] = module
    spec.loader.exec_module(module)

    module.update_semantic_layer()


# DAG Definition
with DAG(
    dag_id=DAG_ID,
    default_args=DEFAULT_ARGS,
    description="Daily product inventory pipeline: Bronze → Silver → Gold",
    schedule_interval=SCHEDULE_INTERVAL,
    start_date=START_DATE,
    catchup=False,
    max_active_runs=1,
    tags=["product", "inventory", "daily", "star-schema"],
    on_failure_callback=failure_callback,
    doc_md=__doc__,
) as dag:

    # Stage 1: Ingest
    with TaskGroup("ingest", tooltip="Validate source data availability") as ingest:
        validate_source_task = PythonOperator(
            task_id="validate_source",
            python_callable=validate_source,
            provide_context=True,
        )

    # Stage 2: Transform
    with TaskGroup("transform", tooltip="Bronze → Silver → Gold transformations") as transform:
        bronze_to_silver_task = PythonOperator(
            task_id="bronze_to_silver",
            python_callable=bronze_to_silver,
            provide_context=True,
            sla=timedelta(hours=1),
        )

        silver_quality_gate_task = PythonOperator(
            task_id="silver_quality_gate",
            python_callable=run_silver_quality_checks,
            provide_context=True,
        )

        silver_to_gold_task = PythonOperator(
            task_id="silver_to_gold",
            python_callable=silver_to_gold,
            provide_context=True,
            sla=timedelta(hours=1),
        )

        gold_quality_gate_task = PythonOperator(
            task_id="gold_quality_gate",
            python_callable=run_gold_quality_checks,
            provide_context=True,
        )

        # Transform stage dependencies
        bronze_to_silver_task >> silver_quality_gate_task >> silver_to_gold_task >> gold_quality_gate_task

    # Stage 3: Publish
    with TaskGroup("publish", tooltip="Register in catalog and update semantic layer") as publish:
        register_catalog_task = PythonOperator(
            task_id="register_catalog",
            python_callable=register_catalog,
            provide_context=True,
        )

        update_semantic_layer_task = PythonOperator(
            task_id="update_semantic_layer",
            python_callable=update_semantic_layer,
            provide_context=True,
        )

        # Publish stage dependencies
        register_catalog_task >> update_semantic_layer_task

    # Pipeline dependencies
    ingest >> transform >> publish
