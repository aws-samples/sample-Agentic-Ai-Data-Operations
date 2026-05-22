"""Entity Resolved Pipeline DAG (manual trigger).

Tool routing decision:
  - Intent: "schedule the pipeline" -> TOOL_ROUTING.md Step 3: airflow-mwaa
  - Deploy: aws s3 sync to MWAA bucket -- DAG appears in Airflow UI
  - Follows: catchup=False, max_active_runs=1, retries=3, exponential backoff
  - Operators from: apache-airflow-providers-amazon

Pipeline (manual trigger only): S3 Sensor -> Bronze Ingest -> Silver Transform -> Quality Gate.

No PII; no Gold zone in this onboarding (per Phase 1 scope: Bronze + Silver).
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.sns import SnsPublishOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from airflow.utils.task_group import TaskGroup

WORKLOAD = "entity_resolved"
GLUE_ROLE = Variable.get("glue_iam_role", default_var="AWS-Glue-job-role")
DATA_LAKE_BUCKET = Variable.get("data_lake_bucket", default_var="data-lake-bucket")
ALERT_TOPIC = Variable.get("alert_sns_topic", default_var="arn:aws:sns:us-east-1:ACCOUNT:alerts")

default_args = {
    "owner": "reference-data-team",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=30),
}


def _on_failure_callback(context):
    """Alert on task failure via SNS."""
    task_instance = context["task_instance"]
    print(
        f"FAILURE: {task_instance.dag_id}.{task_instance.task_id} "
        f"at {context['execution_date']}"
    )


with DAG(
    dag_id=f"{WORKLOAD}_pipeline",
    description="Manual ETL: Bronze -> Silver for entity_resolved reference data",
    # schedule=None: manual trigger only (Phase 1 user decision: ad-hoc upload).
    schedule=None,
    start_date=datetime(2026, 5, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    on_failure_callback=_on_failure_callback,
    tags=[WORKLOAD, "reference-data", "manual"],
    doc_md=__doc__,
) as dag:

    wait_for_source = S3KeySensor(
        task_id="wait_for_source_data",
        bucket_name=DATA_LAKE_BUCKET,
        bucket_key=f"raw/reference/{WORKLOAD}/*.csv",
        poke_interval=300,
        timeout=3600,
        mode="poke",
    )

    with TaskGroup("bronze") as bronze_group:
        ingest = GlueJobOperator(
            task_id="ingest_to_bronze",
            job_name=f"{WORKLOAD}_ingest_to_bronze",
            script_args={
                "--source_bucket": DATA_LAKE_BUCKET,
                "--source_prefix": f"raw/reference/{WORKLOAD}/",
                "--target_bucket": DATA_LAKE_BUCKET,
                "--target_prefix": f"bronze/{WORKLOAD}",
                "--run_id": "{{ run_id }}",
                "--enable-data-lineage": "true",
            },
            iam_role_name=GLUE_ROLE,
        )

    with TaskGroup("silver") as silver_group:
        transform_silver = GlueJobOperator(
            task_id="bronze_to_silver",
            job_name=f"{WORKLOAD}_bronze_to_silver",
            script_args={
                "--data_lake_bucket": DATA_LAKE_BUCKET,
                "--source_database": f"{WORKLOAD}_db",
                "--source_table": f"bronze_{WORKLOAD}",
                "--target_database": f"{WORKLOAD}_db",
                "--target_table": f"silver_{WORKLOAD}",
                "--run_id": "{{ run_id }}",
                "--enable-data-lineage": "true",
            },
            iam_role_name=GLUE_ROLE,
        )

        quality_silver = GlueJobOperator(
            task_id="quality_gate_silver",
            job_name=f"{WORKLOAD}_quality_checks",
            script_args={
                "--database": f"{WORKLOAD}_db",
                "--table": f"silver_{WORKLOAD}",
                "--zone": "silver",
                "--threshold": "0.80",
                "--run_id": "{{ run_id }}",
                "--enable-data-lineage": "true",
            },
            iam_role_name=GLUE_ROLE,
        )

        transform_silver >> quality_silver

    alert_on_failure = SnsPublishOperator(
        task_id="alert_failure",
        target_arn=ALERT_TOPIC,
        subject=f"[FAILED] {WORKLOAD} pipeline",
        message="Pipeline failed. Check Airflow logs for details.",
        trigger_rule="one_failed",
    )

    wait_for_source >> bronze_group >> silver_group >> alert_on_failure
