"""
customer_master_dag.py — Airflow DAG for Customer Master pipeline.

Schedule: Daily at 06:00 UTC
Pipeline: Ingest (Bronze) -> Quality Check (Bronze) -> Transform (Gold) -> Quality Check (Gold) -> Register (Glue)
Owner: CRM Team / Sales
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

# Default args — exponential backoff, failure callback
default_args = {
    "owner": "crm-team",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=60),
    "execution_timeout": timedelta(minutes=60),
}

doc_md = """
## Customer Master Pipeline

**Owner**: CRM Team / Sales
**Schedule**: Daily at 06:00 UTC
**Data Flow**: Bronze (raw CSV) -> Gold (star schema)

### Tables Produced
- `demo_database_ai_agents_goldzone.customer_fact` — One row per unique customer
- `demo_database_ai_agents_goldzone.dim_segment` — Segment dimension
- `demo_database_ai_agents_goldzone.dim_country` — Country dimension
- `demo_database_ai_agents_goldzone.dim_status` — Status dimension
- `demo_database_ai_agents_goldzone.customer_summary_by_segment` — Pre-aggregated metrics

### Quality Gates
- Bronze: score >= 0.80, no critical failures
- Gold: score >= 0.95, no critical failures
"""


def _ingest(**context):
    """Ingest CSV to S3 Bronze zone."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ingest_customers",
        "/opt/airflow/dags/workloads/customer_master/scripts/extract/ingest_customers.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.ingest(upload=True)
    context["ti"].xcom_push(key="ingest_result", value=result)
    return result


def _check_bronze(**context):
    """Run Bronze quality checks."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_bronze",
        "/opt/airflow/dags/workloads/customer_master/scripts/quality/check_bronze.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.run_bronze_checks()
    if not report["gate_passed"]:
        raise ValueError(
            f"Bronze quality gate FAILED: score={report['score']}, "
            f"critical_failures={report['critical_failures']}"
        )
    context["ti"].xcom_push(key="bronze_quality", value=report)
    return report


def _transform(**context):
    """Transform Bronze to Gold star schema."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bronze_to_gold",
        "/opt/airflow/dags/workloads/customer_master/scripts/transform/bronze_to_gold.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.transform(upload=True)
    # Remove non-serializable table data from xcom
    result_clean = {k: v for k, v in result.items() if k != "tables"}
    context["ti"].xcom_push(key="transform_result", value=result_clean)
    return result_clean


def _check_gold(**context):
    """Run Gold quality checks."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_gold",
        "/opt/airflow/dags/workloads/customer_master/scripts/quality/check_gold.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    report = mod.run_gold_checks()
    if not report["gate_passed"]:
        raise ValueError(
            f"Gold quality gate FAILED: score={report['score']}, "
            f"critical_failures={report['critical_failures']}"
        )
    context["ti"].xcom_push(key="gold_quality", value=report)
    return report


def _register_glue(**context):
    """Register tables in Glue Data Catalog."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "register_tables",
        "/opt/airflow/dags/workloads/customer_master/glue/register_tables.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.register_all()
    context["ti"].xcom_push(key="glue_result", value=result)
    return result


with DAG(
    dag_id="customer_master_pipeline",
    default_args=default_args,
    description="Customer Master: Bronze CSV -> Gold star schema with quality gates",
    doc_md=doc_md,
    schedule="0 6 * * *",
    start_date=datetime(2026, 3, 15),
    catchup=False,
    max_active_runs=1,
    tags=["customer", "master-data", "star-schema", "gold"],
) as dag:

    with TaskGroup("bronze_stage") as bronze_stage:
        ingest_task = PythonOperator(
            task_id="ingest_to_bronze",
            python_callable=_ingest,
            sla=timedelta(minutes=10),
        )
        bronze_quality = PythonOperator(
            task_id="bronze_quality_check",
            python_callable=_check_bronze,
            sla=timedelta(minutes=10),
        )
        ingest_task >> bronze_quality

    with TaskGroup("gold_stage") as gold_stage:
        transform_task = PythonOperator(
            task_id="transform_bronze_to_gold",
            python_callable=_transform,
            sla=timedelta(minutes=30),
        )
        gold_quality = PythonOperator(
            task_id="gold_quality_check",
            python_callable=_check_gold,
            sla=timedelta(minutes=10),
        )
        transform_task >> gold_quality

    with TaskGroup("catalog_stage") as catalog_stage:
        register_task = PythonOperator(
            task_id="register_glue_tables",
            python_callable=_register_glue,
            sla=timedelta(minutes=10),
        )

    bronze_stage >> gold_stage >> catalog_stage
