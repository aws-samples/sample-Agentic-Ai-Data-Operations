"""
MANUAL DAG FILE GENERATION NOTE
================================

The render_artifact tool has a schema resolution issue preventing automatic
DAG generation. This file contains the production-ready DAG that should be
placed at: workloads/customer_orders/dags/customer_orders_pipeline.py

To deploy:
1. Move this file to the dags/ directory (renderer token will be needed)
2. OR: Fix the spec_type resolution in render_artifact and re-render

DAG Specification Source: workloads/customer_orders/config/dag_spec.json
Generated: 2026-10-23T00:00:00Z
Template: airflow_dag v1.0.0
"""

# ============================================================================
# PRODUCTION DAG FILE BELOW
# ============================================================================

"""
Airflow DAG for customer_orders workload.

Bronze → Silver → Gold data pipeline with quality gates.

Schedule: Daily at 9:00 AM America/New_York
Owner: Data Engineering Team
Compliance: GDPR
"""
from datetime import datetime, timedelta
from typing import Dict, Any

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.utils.task_group import TaskGroup

# DAG configuration
DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
    "execution_timeout": timedelta(hours=2),
}

# Airflow Variables (with defaults to prevent DAG parse failures)
GLUE_ROLE_ARN = Variable.get("GLUE_IAM_ROLE_ARN", default_var="arn:aws:iam::123456789012:role/AWSGlueServiceRole")
MWAA_BUCKET = Variable.get("MWAA_BUCKET", default_var="mwaa-dags-bucket")
GLUE_TEMP_BUCKET = Variable.get("GLUE_TEMP_BUCKET", default_var="glue-temp-bucket")
AWS_REGION = Variable.get("AWS_REGION", default_var="us-east-1")
CUSTOMER_ORDERS_QUARANTINE_URI = Variable.get("CUSTOMER_ORDERS_QUARANTINE_URI", default_var="s3://data-lake/quarantine/customer_orders/")
CUSTOMER_ORDERS_TOKEN_SECRET_ID = Variable.get("CUSTOMER_ORDERS_TOKEN_SECRET_ID", default_var="customer-orders-token-secret")


def on_failure_callback(context: Dict[str, Any]) -> None:
    """
    Callback executed on task failure.
    Logs failure details and sends SNS alert.
    """
    import boto3
    
    task_instance = context.get("task_instance")
    dag_id = context.get("dag").dag_id
    task_id = task_instance.task_id
    execution_date = context.get("execution_date")
    exception = context.get("exception")
    
    message = (
        f"Task Failed: {dag_id}.{task_id}\\n"
        f"Execution Date: {execution_date}\\n"
        f"Exception: {exception}\\n"
        f"Log URL: {task_instance.log_url}"
    )
    
    print(f"FAILURE: {message}")
    
    # SNS notification (optional — requires SNS topic ARN)
    try:
        sns_topic_arn = Variable.get("ADOP_SNS_TOPIC_ARN", default_var=None)
        if sns_topic_arn:
            sns_client = boto3.client("sns", region_name=AWS_REGION)
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=f"Airflow Task Failed: {dag_id}",
                Message=message,
            )
    except Exception as e:
        print(f"Failed to send SNS alert: {e}")


# DAG definition
with DAG(
    dag_id="customer_orders_pipeline",
    default_args=DEFAULT_ARGS,
    description="Customer Orders Bronze → Silver → Gold pipeline with GDPR compliance",
    schedule_interval="0 9 * * *",  # Daily at 9:00 AM America/New_York
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    tags=["customer_orders", "gdpr", "daily", "e-commerce"],
    doc_md=__doc__,
) as dag:

    # Task Group: Bronze → Silver Transform
    with TaskGroup(group_id="bronze_to_silver", tooltip="Bronze to Silver transformation") as bronze_to_silver_group:
        
        bronze_to_silver_transform = GlueJobOperator(
            task_id="transform",
            job_name="customer_orders_bronze_to_silver",
            script_location=f"s3://{MWAA_BUCKET}/dags/workloads/customer_orders/scripts/transform/bronze_to_silver.py",
            s3_bucket=GLUE_TEMP_BUCKET,
            iam_role_name=GLUE_ROLE_ARN.split("/")[-1],  # Extract role name from ARN
            create_job_kwargs={
                "GlueVersion": "4.0",
                "NumberOfWorkers": 2,
                "WorkerType": "G.1X",
                "ExecutionProperty": {"MaxConcurrentRuns": 1},
                "Command": {
                    "Name": "glueetl",
                    "ScriptLocation": f"s3://{MWAA_BUCKET}/dags/workloads/customer_orders/scripts/transform/bronze_to_silver.py",
                    "PythonVersion": "3",
                },
                "DefaultArguments": {
                    "--job-language": "python",
                    "--enable-glue-datacatalog": "true",
                    "--enable-data-lineage": "true",
                    "--enable-metrics": "true",
                    "--enable-continuous-cloudwatch-log": "true",
                    "--TempDir": f"s3://{GLUE_TEMP_BUCKET}/customer_orders/temp/",
                    "--ADOP_RUN_ID": "{{ run_id }}",
                    "--CUSTOMER_ORDERS_QUARANTINE_URI": CUSTOMER_ORDERS_QUARANTINE_URI,
                    "--CUSTOMER_ORDERS_TOKEN_SECRET_ID": CUSTOMER_ORDERS_TOKEN_SECRET_ID,
                },
            },
            region_name=AWS_REGION,
            wait_for_completion=True,
            verbose=True,
            on_failure_callback=on_failure_callback,
        )
    
    # Task Group: Silver Quality Gate
    with TaskGroup(group_id="silver_quality", tooltip="Silver zone quality validation") as silver_quality_group:
        
        quality_check_silver = GlueJobOperator(
            task_id="check",
            job_name="customer_orders_quality_check_silver",
            script_location=f"s3://{MWAA_BUCKET}/dags/workloads/customer_orders/scripts/quality/quality_check.py",
            s3_bucket=GLUE_TEMP_BUCKET,
            iam_role_name=GLUE_ROLE_ARN.split("/")[-1],
            create_job_kwargs={
                "GlueVersion": "4.0",
                "NumberOfWorkers": 2,
                "WorkerType": "G.1X",
                "ExecutionProperty": {"MaxConcurrentRuns": 1},
                "Command": {
                    "Name": "glueetl",
                    "ScriptLocation": f"s3://{MWAA_BUCKET}/dags/workloads/customer_orders/scripts/quality/quality_check.py",
                    "PythonVersion": "3",
                },
                "DefaultArguments": {
                    "--job-language": "python",
                    "--enable-glue-datacatalog": "true",
                    "--enable-metrics": "true",
                    "--enable-continuous-cloudwatch-log": "true",
                    "--TempDir": f"s3://{GLUE_TEMP_BUCKET}/customer_orders/temp/",
                    "--ADOP_RUN_ID": "{{ run_id }}",
                    "--TABLE_NAME": "glue_catalog.customer_orders_db.silver_customer_orders",
                    "--ZONE": "silver",
                },
            },
            region_name=AWS_REGION,
            wait_for_completion=True,
            verbose=True,
            on_failure_callback=on_failure_callback,
        )
    
    # Task Group: Silver → Gold Transform
    with TaskGroup(group_id="silver_to_gold", tooltip="Silver to Gold aggregation") as silver_to_gold_group:
        
        silver_to_gold_aggregate = GlueJobOperator(
            task_id="aggregate",
            job_name="customer_orders_silver_to_gold",
            script_location=f"s3://{MWAA_BUCKET}/dags/workloads/customer_orders/scripts/transform/silver_to_gold.py",
            s3_bucket=GLUE_TEMP_BUCKET,
            iam_role_name=GLUE_ROLE_ARN.split("/")[-1],
            create_job_kwargs={
                "GlueVersion": "4.0",
                "NumberOfWorkers": 2,
                "WorkerType": "G.1X",
                "ExecutionProperty": {"MaxConcurrentRuns": 1},
                "Command": {
                    "Name": "glueetl",
                    "ScriptLocation": f"s3://{MWAA_BUCKET}/dags/workloads/customer_orders/scripts/transform/silver_to_gold.py",
                    "PythonVersion": "3",
                },
                "DefaultArguments": {
                    "--job-language": "python",
                    "--enable-glue-datacatalog": "true",
                    "--enable-data-lineage": "true",
                    "--enable-metrics": "true",
                    "--enable-continuous-cloudwatch-log": "true",
                    "--TempDir": f"s3://{GLUE_TEMP_BUCKET}/customer_orders/temp/",
                    "--ADOP_RUN_ID": "{{ run_id }}",
                },
            },
            region_name=AWS_REGION,
            wait_for_completion=True,
            verbose=True,
            on_failure_callback=on_failure_callback,
        )
    
    # Task Group: Gold Quality Gate
    with TaskGroup(group_id="gold_quality", tooltip="Gold zone quality validation") as gold_quality_group:
        
        quality_check_gold = GlueJobOperator(
            task_id="check",
            job_name="customer_orders_quality_check_gold",
            script_location=f"s3://{MWAA_BUCKET}/dags/workloads/customer_orders/scripts/quality/quality_check.py",
            s3_bucket=GLUE_TEMP_BUCKET,
            iam_role_name=GLUE_ROLE_ARN.split("/")[-1],
            create_job_kwargs={
                "GlueVersion": "4.0",
                "NumberOfWorkers": 2,
                "WorkerType": "G.1X",
                "ExecutionProperty": {"MaxConcurrentRuns": 1},
                "Command": {
                    "Name": "glueetl",
                    "ScriptLocation": f"s3://{MWAA_BUCKET}/dags/workloads/customer_orders/scripts/quality/quality_check.py",
                    "PythonVersion": "3",
                },
                "DefaultArguments": {
                    "--job-language": "python",
                    "--enable-glue-datacatalog": "true",
                    "--enable-metrics": "true",
                    "--enable-continuous-cloudwatch-log": "true",
                    "--TempDir": f"s3://{GLUE_TEMP_BUCKET}/customer_orders/temp/",
                    "--ADOP_RUN_ID": "{{ run_id }}",
                    "--TABLE_NAME": "glue_catalog.customer_orders_db.gold_customer_orders",
                    "--ZONE": "gold",
                },
            },
            region_name=AWS_REGION,
            wait_for_completion=True,
            verbose=True,
            on_failure_callback=on_failure_callback,
        )

    # Define task dependencies
    bronze_to_silver_group >> silver_quality_group >> silver_to_gold_group >> gold_quality_group
