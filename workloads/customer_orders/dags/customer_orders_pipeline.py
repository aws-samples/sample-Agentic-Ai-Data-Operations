# spec_hash: cafce3fa9727dd7a3b3d03a2028a0d28a23e221249a182fb8b317e69c4335915
# template_id: airflow_dag
# template_hash: 4a691614e0804fdf8290b94de9863e1d4117a11b5b09b323f9ad27515011df4a
# schema_version: v1
# rendered_at: 2026-10-23T00:00:00Z
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
                default_var="{{ var.value.ADOP_SNS_ALERT_TOPIC }}",
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

DAG_ID = "customer_orders_pipeline"

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="customer_orders data pipeline (Bronze → Silver → Gold)",
    schedule_interval="0 9 * * *",
    dagrun_timeout=timedelta(minutes=180),
    start_date=pendulum.datetime(
        2026,
        10,
        22,
        tz="America/New_York",
    ),
    catchup=False,
    max_active_runs=1,
    tags=["customer_orders", "gdpr", "daily", "bronze_silver_gold"],
) as dag:

    bronze_to_silver = GlueJobOperator(
        task_id="bronze_to_silver",
        job_name="customer_orders_bronze_to_silver",
        script_location=f"{GLUE_SCRIPT_S3_PATH}workloads/customer_orders/scripts/transform/bronze_to_silver.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        execution_timeout=timedelta(minutes=60),
        script_args={
    "job_name": "customer_orders_bronze_to_silver",
    "glue_version": "4.0",
    "worker_type": "G.1X",
    "number_of_workers": 2,
    "arguments": {"--ADOP_RUN_ID": "{{ run_id }}", "--CUSTOMER_ORDERS_QUARANTINE_URI": "{{ var.value.CUSTOMER_ORDERS_QUARANTINE_URI }}", "--CUSTOMER_ORDERS_TOKEN_SECRET_ID": "{{ var.value.CUSTOMER_ORDERS_TOKEN_SECRET_ID }}", "--enable-data-lineage": "true", "--enable-glue-datacatalog": "true"},
    "--ADOP_RUN_ID": "{{ run_id }}"
},
    )

    quality_check_silver = GlueJobOperator(
        task_id="quality_check_silver",
        job_name="customer_orders_quality_check_silver",
        script_location=f"{GLUE_SCRIPT_S3_PATH}workloads/customer_orders/scripts/quality/check_silver.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        script_args={
    "zone": "silver",
    "threshold": 0.8,
    "table_name": "glue_catalog.customer_orders_db.silver_customer_orders",
    "quality_rules_path": "workloads/customer_orders/config/quality_rules.yaml",
    "--ADOP_RUN_ID": "{{ run_id }}"
},
        execution_timeout=timedelta(minutes=30),
    )

    silver_to_gold = GlueJobOperator(
        task_id="silver_to_gold",
        job_name="customer_orders_silver_to_gold",
        script_location=f"{GLUE_SCRIPT_S3_PATH}workloads/customer_orders/scripts/transform/silver_to_gold.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        execution_timeout=timedelta(minutes=60),
        script_args={
    "job_name": "customer_orders_silver_to_gold",
    "glue_version": "4.0",
    "worker_type": "G.1X",
    "number_of_workers": 2,
    "arguments": {"--ADOP_RUN_ID": "{{ run_id }}", "--enable-data-lineage": "true", "--enable-glue-datacatalog": "true"},
    "--ADOP_RUN_ID": "{{ run_id }}"
},
    )

    quality_check_gold = GlueJobOperator(
        task_id="quality_check_gold",
        job_name="customer_orders_quality_check_gold",
        script_location=f"{GLUE_SCRIPT_S3_PATH}workloads/customer_orders/scripts/quality/check_gold.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="${AWS_REGION}"),
        script_args={
    "zone": "gold",
    "threshold": 0.95,
    "table_name": "glue_catalog.customer_orders_db.gold_customer_orders",
    "quality_rules_path": "workloads/customer_orders/config/quality_rules.yaml",
    "--ADOP_RUN_ID": "{{ run_id }}"
},
        execution_timeout=timedelta(minutes=30),
    )

    # Task dependencies
    bronze_to_silver >> quality_check_silver
    quality_check_silver >> silver_to_gold
    silver_to_gold >> quality_check_gold
