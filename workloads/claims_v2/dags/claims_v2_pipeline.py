# spec_hash: cd5c5162b485e223f2f39ad363719f5397b0b7aa2c11e0e247b85e2e541dd9d6
# template_id: airflow_dag
# template_hash: bb35cd4c35617b65f82f484a41d18068110a2ff660f296bc82c4679586dde0b9
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

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(seconds=300),
    "max_retry_delay": timedelta(seconds=3600),
    "retry_exponential_backoff": True,
    "email_on_failure": False,
}

DAG_ID = "claims_v2_pipeline"

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="claims_v2 data pipeline (Bronze → Silver → Gold)",
    schedule_interval="0 6 * * *",
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
        script_location=f"{GLUE_SCRIPT_S3_PATH}quality_check.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        script_args={"--TABLE_NAME": "glue_catalog.claims_v2_db.silver_claims_v2", "--ZONE": "silver"},
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
        script_location=f"{GLUE_SCRIPT_S3_PATH}quality_check.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        script_args={"--TABLE_NAME": "glue_catalog.claims_v2_db.gold_claims_v2", "--ZONE": "gold"},
    )

    # Task dependencies
    ingest_bronze >> transform_silver
    transform_silver >> quality_check_silver
    quality_check_silver >> aggregate_gold
    aggregate_gold >> quality_check_gold
