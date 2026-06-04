"""
Customer Master Pipeline DAG — Bronze -> Silver -> Gold
Schedule: Daily at 02:00 UTC
Compliance: CCPA + GDPR dual-compliance
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.sensors.glue import GlueJobSensor
from airflow.utils.task_group import TaskGroup

WORKLOAD = "customer_master"
DATABASE = "customer_master_db"

GLUE_SCRIPT_PATH = Variable.get(
    "glue_script_s3_path",
    default_var="s3://glue-scripts-bucket/customer_master/",
)
GLUE_ROLE = Variable.get(
    "glue_iam_role", default_var="AWSGlueServiceRole"
)
AWS_ACCOUNT_ID = Variable.get(
    "aws_account_id", default_var="<ACCOUNT_ID>"
)
ALERT_SNS_TOPIC = Variable.get(
    "alert_sns_topic",
    default_var=f"arn:aws:sns:us-east-1:{AWS_ACCOUNT_ID}:data-pipeline-alerts",
)


def on_failure_callback(context):
    """Send SNS alert on task failure."""
    import boto3

    sns = boto3.client("sns")
    task_instance = context["task_instance"]
    sns.publish(
        TopicArn=ALERT_SNS_TOPIC,
        Subject=f"PIPELINE FAILURE: {WORKLOAD}",
        Message=(
            f"Task: {task_instance.task_id}\n"
            f"DAG: {task_instance.dag_id}\n"
            f"Execution: {context['execution_date']}\n"
            f"Log URL: {task_instance.log_url}"
        ),
    )


default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=60),
    "on_failure_callback": on_failure_callback,
}

with DAG(
    dag_id=f"{WORKLOAD}_pipeline",
    default_args=default_args,
    description="Customer Master: Bronze -> Silver -> Gold (CCPA+GDPR)",
    schedule_interval="0 2 * * *",
    start_date=datetime(2026, 6, 3),
    catchup=False,
    max_active_runs=1,
    tags=["customer_master", "ccpa", "gdpr", "daily"],
    doc_md="""
    ## Customer Master Pipeline

    **Source**: s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/customer_master.csv
    **Schedule**: Daily 02:00 UTC
    **Compliance**: CCPA + GDPR dual-compliance

    ### Stages
    1. Bronze ingestion (raw CSV -> Iceberg)
    2. Silver transform (dedup, PII mask, derive columns)
    3. Quality gate (score >= 0.80)
    4. Gold aggregation (dim_customer star schema)
    5. Gold quality gate (score >= 0.95)

    ### PII Controls
    - Silver: SSN hashed (SHA-256), email/phone hashed, DOB/address redacted
    - Gold: SSN suppressed, email domain-only, phone suppressed, address city+state+zip only
    """,
) as dag:

    with TaskGroup("bronze_ingestion") as bronze_group:
        ingest_bronze = GlueJobOperator(
            task_id="ingest_to_bronze",
            job_name=f"{WORKLOAD}_bronze_ingest",
            script_location=f"{GLUE_SCRIPT_PATH}extract/ingest_bronze.py",
            iam_role_name=GLUE_ROLE,
            region_name="us-east-1",
            num_of_dpus=2,
            script_args={
                "--source_path": "s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/customer_master.csv",
                "--target_database": DATABASE,
                "--target_table": "bronze_customer_master",
            },
            sla=timedelta(minutes=15),
        )

    with TaskGroup("silver_transform") as silver_group:
        transform_silver = GlueJobOperator(
            task_id="bronze_to_silver",
            job_name=f"{WORKLOAD}_silver_transform",
            script_location=f"{GLUE_SCRIPT_PATH}transform/bronze_to_silver.py",
            iam_role_name=GLUE_ROLE,
            region_name="us-east-1",
            num_of_dpus=2,
            script_args={
                "--source_table": f"glue_catalog.{DATABASE}.bronze_customer_master",
                "--target_database": DATABASE,
                "--target_table": "silver_customer_master",
            },
            sla=timedelta(minutes=30),
        )

    with TaskGroup("silver_quality") as silver_quality_group:
        quality_silver = GlueJobOperator(
            task_id="quality_check_silver",
            job_name=f"{WORKLOAD}_silver_quality",
            script_location=f"{GLUE_SCRIPT_PATH}quality/glue_data_quality.py",
            iam_role_name=GLUE_ROLE,
            region_name="us-east-1",
            num_of_dpus=2,
            script_args={
                "--action": "run-evaluation",
                "--zone": "silver",
            },
            sla=timedelta(minutes=15),
        )

    with TaskGroup("gold_aggregation") as gold_group:
        transform_gold = GlueJobOperator(
            task_id="silver_to_gold",
            job_name=f"{WORKLOAD}_gold_aggregate",
            script_location=f"{GLUE_SCRIPT_PATH}transform/silver_to_gold.py",
            iam_role_name=GLUE_ROLE,
            region_name="us-east-1",
            num_of_dpus=2,
            script_args={
                "--source_table": f"glue_catalog.{DATABASE}.silver_customer_master",
                "--target_database": DATABASE,
                "--target_table": "dim_customer",
            },
            sla=timedelta(minutes=30),
        )

    with TaskGroup("gold_quality") as gold_quality_group:
        quality_gold = GlueJobOperator(
            task_id="quality_check_gold",
            job_name=f"{WORKLOAD}_gold_quality",
            script_location=f"{GLUE_SCRIPT_PATH}quality/glue_data_quality.py",
            iam_role_name=GLUE_ROLE,
            region_name="us-east-1",
            num_of_dpus=2,
            script_args={
                "--action": "run-evaluation",
                "--zone": "gold",
            },
            sla=timedelta(minutes=15),
        )

    bronze_group >> silver_group >> silver_quality_group >> gold_group >> gold_quality_group
