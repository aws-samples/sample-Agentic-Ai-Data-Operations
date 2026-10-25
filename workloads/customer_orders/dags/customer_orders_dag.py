# spec_hash: 5324aefe245aac864a639e0ab18e0d32628a6cf9efdb75ac13da4fa24d8c71aa
# template_id: airflow_dag
# template_hash: 4a691614e0804fdf8290b94de9863e1d4117a11b5b09b323f9ad27515011df4a
# schema_version: v2
# rendered_at: 2026-10-22T18:18:44Z
from datetime import timedelta

import pendulum

from airflow import DAG
from airflow.models import Variable
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator

GLUE_SCRIPT_S3_PATH = Variable.get("glue_script_s3_path", default_var="${GLUE_SCRIPT_S3_PATH}")
GLUE_IAM_ROLE = Variable.get("glue_iam_role", default_var="${GLUE_IAM_ROLE}")



def _notify_failure(context):
    """on_failure_callback: publish the failed task to SNS.

    Wired from failure_handling.on_failure_callback. Before this existed a task could fail
    and nobody was told — default_args carried only email_on_failure=False, and with
    retries=0 there was no retry to notice either.

    Never raises: an alerting failure must not mask the task failure it is reporting.
    """
    import boto3

    ti = context.get("task_instance")
    try:
        boto3.client("sns").publish(
            TopicArn=Variable.get(
                "customer_orders_alert_sns_topic",
                default_var="customer_orders_alerts",
            ),
            Subject=f"ADOP customer_orders task failed: {ti.task_id if ti else 'unknown'}",
            Message=(
                f"dag={context.get('dag').dag_id if context.get('dag') else DAG_ID}\n"
                f"task={ti.task_id if ti else 'unknown'}\n"
                f"run={context.get('run_id')}\n"
                f"log={ti.log_url if ti else 'unknown'}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"_notify_failure: could not publish to SNS: {exc}")




default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(seconds=300),
    "max_retry_delay": timedelta(seconds=3600),
    "retry_exponential_backoff": True,
    "email_on_failure": False,
    "on_failure_callback": _notify_failure,
}

DAG_ID = "customer_orders_daily"

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="customer_orders data pipeline (Bronze → Silver → Gold)",
    schedule_interval="0 9 * * *",
    dagrun_timeout=timedelta(minutes=15),
    start_date=pendulum.datetime(
        2026,
        1,
        1,
        tz="America/New_York",
    ),
    catchup=False,
    max_active_runs=1,
    tags=["customer_orders", "data-pipeline", "gdpr", "demo-only"],
) as dag:

    ingest_bronze = GlueJobOperator(
        task_id="ingest_bronze",
        job_name="customer_orders_ingest_bronze",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/extract/bronze_ingestion.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        execution_timeout=timedelta(minutes=15),
        script_args={
    "--CUSTOMER_ORDERS_SOURCE_URI": Variable.get("CUSTOMER_ORDERS_SOURCE_URI", default_var=""),
    "--DATA_LAKE_BUCKET": Variable.get("DATA_LAKE_BUCKET", default_var=""),
    "--ADOP_RUN_ID": "{{ run_id }}"
},
    )

    transform_bronze_to_silver = GlueJobOperator(
        task_id="transform_bronze_to_silver",
        job_name="customer_orders_transform_bronze_to_silver",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/transform/bronze_to_silver.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        execution_timeout=timedelta(minutes=15),
        script_args={
    "--CUSTOMER_ORDERS_QUARANTINE_URI": Variable.get("CUSTOMER_ORDERS_QUARANTINE_URI", default_var=""),
    "--CUSTOMER_ORDERS_TOKEN_SECRET_ID": Variable.get("CUSTOMER_ORDERS_TOKEN_SECRET_ID", default_var=""),
    "--ADOP_RUN_ID": "{{ run_id }}"
},
    )

    quality_check_silver = GlueJobOperator(
        task_id="quality_check_silver",
        job_name="customer_orders_quality_check_silver",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/quality/quality_check.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        script_args={
    "--TABLE_NAME": "glue_catalog.customer_orders_db.silver_customer_orders",
    "--ZONE": "silver",
    "--ADOP_RUN_ID": "{{ run_id }}"
},
        execution_timeout=timedelta(minutes=15),
    )

    transform_silver_to_gold = GlueJobOperator(
        task_id="transform_silver_to_gold",
        job_name="customer_orders_transform_silver_to_gold",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/transform/silver_to_gold.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        execution_timeout=timedelta(minutes=15),
        script_args={
    "--ADOP_RUN_ID": "{{ run_id }}"
},
    )

    quality_check_gold = GlueJobOperator(
        task_id="quality_check_gold",
        job_name="customer_orders_quality_check_gold",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/quality/quality_check.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        script_args={
    "--TABLE_NAME": "glue_catalog.customer_orders_db.gold_customer_orders",
    "--ZONE": "gold",
    "--ADOP_RUN_ID": "{{ run_id }}"
},
        execution_timeout=timedelta(minutes=15),
    )

    # Task dependencies
    ingest_bronze >> transform_bronze_to_silver
    transform_bronze_to_silver >> quality_check_silver
    quality_check_silver >> transform_silver_to_gold
    transform_silver_to_gold >> quality_check_gold
