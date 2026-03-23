"""
Financial Portfolios Pipeline DAG

Daily data pipeline for financial portfolio management:
Bronze (CSV) → Silver (Iceberg) → Gold (Star Schema Iceberg)

Tables:
- stocks: Stock master data (ticker, company, sector, industry)
- portfolios: Portfolio master data (portfolio_id, name, manager, strategy)
- positions: Position details (portfolio_id, ticker, shares, prices, gains/losses)

Schedule: Daily at 9:00 AM EST (14:00 UTC)
SLA: 30 minutes
SOX Compliance: Required
"""

from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
from airflow.utils.dates import days_ago
from airflow.models import Variable
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# DAG default args
default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'email': [Variable.get('data_team_email', default_var='data-team@company.com')],
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
    'execution_timeout': timedelta(minutes=30),
}

def failure_callback(context):
    """Alert on pipeline failures"""
    task_instance = context['task_instance']
    dag_run = context['dag_run']

    logger.error(
        f"Task {task_instance.task_id} failed in DAG {dag_run.dag_id} "
        f"(Run ID: {dag_run.run_id})"
    )

    # Send alerts via configured channels
    # Implementation would integrate with Slack, PagerDuty, etc.
    pass

def run_quality_checks(zone: str, **context):
    """
    Execute quality checks for specified data zone.

    Args:
        zone: Data zone to check ('silver' or 'gold')
    """
    import sys
    import os

    # Add project root to path for imports
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    sys.path.insert(0, project_root)

    from shared.utils.quality_checks import QualityChecker

    workload = "financial_portfolios"
    checker = QualityChecker(workload)

    if zone == 'silver':
        tables = ['stocks', 'portfolios', 'positions']
    elif zone == 'gold':
        tables = ['dim_stocks', 'dim_portfolios', 'fact_positions', 'portfolio_summary']
    else:
        raise ValueError(f"Invalid zone: {zone}")

    # Run quality checks
    results = checker.run_checks(zone=zone, tables=tables)

    # Check for failures
    critical_failures = [r for r in results if r['severity'] == 'critical' and not r['passed']]
    if critical_failures:
        raise Exception(
            f"Quality gate failed: {len(critical_failures)} critical checks failed. "
            f"Details: {critical_failures}"
        )

    # Check overall score
    avg_score = sum(r['score'] for r in results) / len(results)
    threshold = 0.95 if zone == 'gold' else 0.80

    if avg_score < threshold:
        raise Exception(
            f"Quality gate failed: Average score {avg_score:.2f} below threshold {threshold}"
        )

    logger.info(f"{zone.upper()} quality checks passed: {len(results)} checks, avg score {avg_score:.2f}")
    return results

def refresh_quicksight_dashboards(**context):
    """Refresh QuickSight datasets and dashboards"""
    import boto3

    quicksight = boto3.client('quicksight')
    account_id = Variable.get('aws_account_id', default_var='000000000000')

    # Refresh datasets
    datasets = [
        'fact_positions',
        'dim_stocks',
        'dim_portfolios',
        'portfolio_summary'
    ]

    for dataset_id in datasets:
        try:
            response = quicksight.create_ingestion(
                DataSetId=dataset_id,
                IngestionId=f"ingestion_{context['ds_nodash']}",
                AwsAccountId=account_id
            )
            logger.info(f"Triggered refresh for dataset {dataset_id}: {response['IngestionId']}")
        except Exception as e:
            logger.error(f"Failed to refresh dataset {dataset_id}: {str(e)}")
            # Don't fail the task on dashboard refresh errors

    logger.info("QuickSight dashboard refresh completed")

# Create DAG
with DAG(
    dag_id='financial_portfolios_pipeline',
    default_args=default_args,
    description='Daily financial portfolio data pipeline: Bronze → Silver → Gold',
    schedule_interval='0 14 * * *',  # Daily at 9:00 AM EST
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=['finance', 'portfolios', 'sox-compliant'],
    doc_md=__doc__,
    on_failure_callback=failure_callback,
) as dag:

    # Task Group 1: Bronze Ingestion
    with TaskGroup('bronze_ingestion', tooltip='Ingest CSV files to Bronze zone') as bronze_ingestion:

        ingest_stocks = GlueJobOperator(
            task_id='ingest_stocks',
            job_name=Variable.get('glue_job_bronze_stocks', default_var='financial_portfolios_bronze_stocks'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/bronze/ingest_stocks.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'stocks',
                '--execution_date': '{{ ds }}',
            },
        )

        ingest_portfolios = GlueJobOperator(
            task_id='ingest_portfolios',
            job_name=Variable.get('glue_job_bronze_portfolios', default_var='financial_portfolios_bronze_portfolios'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/bronze/ingest_portfolios.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'portfolios',
                '--execution_date': '{{ ds }}',
            },
        )

        ingest_positions = GlueJobOperator(
            task_id='ingest_positions',
            job_name=Variable.get('glue_job_bronze_positions', default_var='financial_portfolios_bronze_positions'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/bronze/ingest_positions.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'positions',
                '--execution_date': '{{ ds }}',
            },
        )

    # Task Group 2: Silver Transformation
    with TaskGroup('silver_transformation', tooltip='Clean and validate: Bronze → Silver') as silver_transformation:

        transform_stocks = GlueJobOperator(
            task_id='transform_stocks_to_silver',
            job_name=Variable.get('glue_job_silver_stocks', default_var='financial_portfolios_silver_stocks'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/silver/transform_stocks.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'stocks',
                '--execution_date': '{{ ds }}',
            },
        )

        transform_portfolios = GlueJobOperator(
            task_id='transform_portfolios_to_silver',
            job_name=Variable.get('glue_job_silver_portfolios', default_var='financial_portfolios_silver_portfolios'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/silver/transform_portfolios.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'portfolios',
                '--execution_date': '{{ ds }}',
            },
        )

        transform_positions = GlueJobOperator(
            task_id='transform_positions_to_silver',
            job_name=Variable.get('glue_job_silver_positions', default_var='financial_portfolios_silver_positions'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/silver/transform_positions.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'positions',
                '--execution_date': '{{ ds }}',
            },
        )

    # Quality Gate 1: Silver Quality Checks
    quality_check_silver = PythonOperator(
        task_id='quality_check_silver',
        python_callable=run_quality_checks,
        op_kwargs={'zone': 'silver'},
        provide_context=True,
        sla=timedelta(minutes=10),
    )

    # Task Group 3: Gold Transformation (Star Schema)
    with TaskGroup('gold_transformation', tooltip='Build star schema: Silver → Gold') as gold_transformation:

        transform_dim_stocks = GlueJobOperator(
            task_id='transform_dim_stocks',
            job_name=Variable.get('glue_job_gold_dim_stocks', default_var='financial_portfolios_gold_dim_stocks'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/gold/transform_dim_stocks.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'dim_stocks',
                '--execution_date': '{{ ds }}',
            },
        )

        transform_dim_portfolios = GlueJobOperator(
            task_id='transform_dim_portfolios',
            job_name=Variable.get('glue_job_gold_dim_portfolios', default_var='financial_portfolios_gold_dim_portfolios'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/gold/transform_dim_portfolios.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'dim_portfolios',
                '--execution_date': '{{ ds }}',
            },
        )

        transform_fact_positions = GlueJobOperator(
            task_id='transform_fact_positions',
            job_name=Variable.get('glue_job_gold_fact_positions', default_var='financial_portfolios_gold_fact_positions'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/gold/transform_fact_positions.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'fact_positions',
                '--execution_date': '{{ ds }}',
            },
        )

        transform_portfolio_summary = GlueJobOperator(
            task_id='transform_portfolio_summary',
            job_name=Variable.get('glue_job_gold_summary', default_var='financial_portfolios_gold_summary'),
            script_location=Variable.get('glue_script_s3_path', default_var='s3://data-lake-ACCOUNT-us-east-1/scripts/financial_portfolios') + '/gold/transform_portfolio_summary.py',
            iam_role_name=Variable.get('glue_iam_role', default_var='AWSGlueServiceRole-FinancialPortfolios'),
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
            },
            script_args={
                '--workload': 'financial_portfolios',
                '--table': 'portfolio_summary',
                '--execution_date': '{{ ds }}',
            },
        )

        # Dependencies within gold transformation
        [transform_dim_stocks, transform_dim_portfolios] >> transform_fact_positions
        transform_fact_positions >> transform_portfolio_summary

    # Quality Gate 2: Gold Quality Checks
    quality_check_gold = PythonOperator(
        task_id='quality_check_gold',
        python_callable=run_quality_checks,
        op_kwargs={'zone': 'gold'},
        provide_context=True,
        sla=timedelta(minutes=10),
    )

    # Dashboard Refresh
    refresh_dashboards = PythonOperator(
        task_id='refresh_quicksight_datasets',
        python_callable=refresh_quicksight_dashboards,
        provide_context=True,
    )

    # Define overall pipeline dependencies
    bronze_ingestion >> silver_transformation >> quality_check_silver
    quality_check_silver >> gold_transformation >> quality_check_gold
    quality_check_gold >> refresh_dashboards
