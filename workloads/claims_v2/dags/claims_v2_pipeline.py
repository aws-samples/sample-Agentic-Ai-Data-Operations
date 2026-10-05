# spec_hash: a6033aee2989ac38e61a8c22d51291d68fc906de15509b5fd1ee5366acfd5484
# template_id: airflow_dag
# template_hash: cb634f5f910bf87e6113820d067df64eecc844e1b5c85911f6269320bcb4f86d
# schema_version: v1
# rendered_at: 2026-05-21T06:00:00Z
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator

GLUE_SCRIPT_S3_PATH = Variable.get("glue_script_s3_path", default_var="s3://glue-scripts/")
GLUE_IAM_ROLE = Variable.get("glue_iam_role", default_var="AWSGlueServiceRole")



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
                "claims_v2_alert_sns_topic",
                default_var="claims-pipeline-alerts",
            ),
            Subject=f"ADOP claims_v2 task failed: {ti.task_id if ti else 'unknown'}",
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

DAG_ID = "claims_v2_pipeline"

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="claims_v2 data pipeline (Bronze → Silver → Gold)",
    schedule_interval="0 6 * * *",
    dagrun_timeout=timedelta(minutes=120),
    start_date=datetime.fromisoformat("2026-01-01"),
    catchup=False,
    max_active_runs=1,
    tags=["claims", "healthcare", "hipaa", "data-pipeline"],
) as dag:

    ingest_bronze = GlueJobOperator(
        task_id="ingest_bronze",
        job_name="claims_v2_ingest_bronze",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/extract/ingest_claims.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        execution_timeout=timedelta(minutes=30),
    )

    transform_silver = GlueJobOperator(
        task_id="transform_silver",
        job_name="claims_v2_transform_silver",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/transform/bronze_to_silver.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        execution_timeout=timedelta(minutes=45),
    )

    quality_check_silver = GlueJobOperator(
        task_id="quality_check_silver",
        job_name="claims_v2_quality_check_silver",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/quality/check_quality.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        script_args={"--TABLE_NAME": "glue_catalog.claims_v2_db.silver_claims_v2", "--ZONE": "silver"},
        execution_timeout=timedelta(minutes=15),
    )

    aggregate_gold = GlueJobOperator(
        task_id="aggregate_gold",
        job_name="claims_v2_aggregate_gold",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/transform/silver_to_gold.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        execution_timeout=timedelta(minutes=30),
    )

    quality_check_gold = GlueJobOperator(
        task_id="quality_check_gold",
        job_name="claims_v2_quality_check_gold",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/quality/check_quality.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        script_args={"--TABLE_NAME": "glue_catalog.claims_v2_db.gold_claims_v2", "--ZONE": "gold"},
        execution_timeout=timedelta(minutes=15),
    )

    # Task dependencies
    ingest_bronze >> transform_silver
    transform_silver >> quality_check_silver
    quality_check_silver >> aggregate_gold
    aggregate_gold >> quality_check_gold
