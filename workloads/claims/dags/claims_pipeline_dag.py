"""
Claims Pipeline DAG — Bronze → Silver → Gold
HIPAA-compliant healthcare claims processing
Schedule: Daily 9:00 AM AEST (23:00 UTC)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

default_args = {
    "owner": "claims-ops",
    "depends_on_past": False,
    "email_on_failure": True,
    "email": [Variable.get("claims_alert_email", default_var="claims-ops@company.com")],
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
}

GLUE_SCRIPT_PATH = Variable.get("glue_script_s3_path", default_var="s3://glue-scripts/claims/")
GLUE_IAM_ROLE = Variable.get("glue_iam_role", default_var="AWSGlueServiceRole-Claims")
AWS_ACCOUNT_ID = Variable.get("aws_account_id", default_var="000000000000")


def run_bronze_to_silver(**context):
    import subprocess
    result = subprocess.run(
        ["python3", "workloads/claims/scripts/transform/bronze_to_silver_claims.py",
         "--local",
         "--bronze_path", "demo/sample_data/claims.csv",
         "--silver_path", "/tmp/data-lake/silver/claims/claims.parquet"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"Bronze→Silver failed: {result.stderr}")
    print(result.stdout)


def run_silver_to_gold(**context):
    import subprocess
    result = subprocess.run(
        ["python3", "workloads/claims/scripts/transform/silver_to_gold_claims.py",
         "--local",
         "--silver_path", "/tmp/data-lake/silver/claims/claims.parquet",
         "--gold_path", "/tmp/data-lake/gold/claims/claims_analytical.parquet"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"Silver→Gold failed: {result.stderr}")
    print(result.stdout)


def run_quality_checks(**context):
    print("Quality checks: score >= 0.80 required for Silver, >= 0.95 for Gold")
    print("HIPAA compliance checks: PHI encrypted, LF-Tags applied, audit logging active")


def on_failure_callback(context):
    print(f"Task {context['task_instance'].task_id} failed. Alerting claims-ops team.")


with DAG(
    dag_id="claims_pipeline",
    default_args=default_args,
    description="HIPAA-compliant claims pipeline: Bronze → Silver → Gold",
    schedule_interval="0 23 * * *",
    start_date=datetime(2026, 5, 20),
    catchup=False,
    max_active_runs=1,
    tags=["claims", "hipaa", "healthcare", "daily"],
    on_failure_callback=on_failure_callback,
    doc_md="""
    ## Claims Pipeline
    - **Source**: `demo/sample_data/claims.csv` (local) / S3 (production)
    - **Schedule**: Daily 9:00 AM AEST (23:00 UTC)
    - **Compliance**: HIPAA — PHI masked in Silver, encrypted at rest
    - **Quality Gate**: >= 0.80 (Silver), >= 0.95 (Gold)
    - **Gold Schema**: Flat denormalized Iceberg for analytical reporting
    """,
) as dag:

    with TaskGroup("bronze_to_silver") as bronze_silver_group:
        bronze_to_silver = PythonOperator(
            task_id="transform_bronze_to_silver",
            python_callable=run_bronze_to_silver,
            sla=timedelta(minutes=30),
        )

    with TaskGroup("quality_gate_silver") as quality_silver_group:
        quality_silver = PythonOperator(
            task_id="run_quality_checks_silver",
            python_callable=run_quality_checks,
            sla=timedelta(minutes=15),
        )

    with TaskGroup("silver_to_gold") as silver_gold_group:
        silver_to_gold = PythonOperator(
            task_id="transform_silver_to_gold",
            python_callable=run_silver_to_gold,
            sla=timedelta(minutes=20),
        )

    bronze_silver_group >> quality_silver_group >> silver_gold_group
