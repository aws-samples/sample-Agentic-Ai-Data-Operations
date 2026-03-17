"""
Airflow DAG for order_transactions pipeline.

Schedule: Daily at 07:00 UTC (after customer_master completes)
Flow: ExternalTaskSensor(customer_master) -> Ingest -> Quality(Bronze) -> Transform -> Quality(Gold) -> Register

Configuration:
- catchup=False, max_active_runs=1
- retries=3 with exponential backoff
- ExternalTaskSensor waits for customer_master_pipeline completion
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.utils.task_group import TaskGroup

# Default arguments
default_args = {
    "owner": "data-engineering",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=60),
    "depends_on_past": False,
}

doc_md = """
## Order Transactions Pipeline

**Workload**: order_transactions
**Schedule**: Daily at 07:00 UTC
**Depends on**: customer_master_pipeline (ExternalTaskSensor)

### Pipeline Steps
1. **Wait for customer_master**: ExternalTaskSensor ensures customer data is fresh
2. **Ingest**: Upload raw CSV to S3 Bronze zone
3. **Bronze Quality**: Validate raw data (completeness, uniqueness, validity, consistency)
4. **Transform**: Bronze-to-Gold star schema (dedup, FK validation, future date quarantine)
5. **Gold Quality**: Validate star schema (referential integrity, no future dates, no orphans)
6. **Register**: Register/update Glue Catalog tables

### Quality Gates
- Bronze: Informational (no blocking)
- Gold: Score >= 0.95, no critical failures (blocks promotion)

### Star Schema
- **order_fact**: One row per clean order with FK to dimensions
- **dim_product**: Product name + category
- **dim_region**: Sales regions (East, West, Central, South)
- **dim_status**: Order statuses (Completed, Pending, Cancelled)
- **order_summary**: Pre-aggregated metrics by region + category
"""

with DAG(
    dag_id="order_transactions_pipeline",
    default_args=default_args,
    description="Order transactions Bronze-to-Gold pipeline with star schema",
    schedule_interval="0 7 * * *",
    start_date=datetime(2026, 3, 1),
    catchup=False,
    max_active_runs=1,
    tags=["order_transactions", "sales", "star_schema"],
    doc_md=doc_md,
) as dag:

    # Wait for customer_master to complete
    wait_for_customer_master = ExternalTaskSensor(
        task_id="wait_for_customer_master",
        external_dag_id="customer_master_pipeline",
        external_task_id=None,  # Wait for entire DAG
        timeout=3600,  # 1 hour
        poke_interval=60,
        mode="reschedule",
    )

    with TaskGroup("ingest") as ingest_group:
        ingest_task = PythonOperator(
            task_id="extract_orders",
            python_callable=lambda: __import__(
                "workloads.order_transactions.scripts.extract.ingest_orders",
                fromlist=["ingest"],
            ).ingest(),
        )

    with TaskGroup("quality_bronze") as quality_bronze_group:
        check_bronze_task = PythonOperator(
            task_id="check_bronze",
            python_callable=lambda: __import__(
                "workloads.order_transactions.scripts.quality.check_bronze",
                fromlist=["check_bronze"],
            ).check_bronze(),
        )

    with TaskGroup("transform") as transform_group:
        transform_task = PythonOperator(
            task_id="bronze_to_gold",
            python_callable=lambda: __import__(
                "workloads.order_transactions.scripts.transform.bronze_to_gold",
                fromlist=["transform"],
            ).transform(),
        )

    with TaskGroup("quality_gold") as quality_gold_group:
        check_gold_task = PythonOperator(
            task_id="check_gold",
            python_callable=lambda: __import__(
                "workloads.order_transactions.scripts.quality.check_gold",
                fromlist=["check_gold"],
            ).check_gold(),
        )

    with TaskGroup("register") as register_group:
        register_task = PythonOperator(
            task_id="register_glue_tables",
            python_callable=lambda: __import__(
                "workloads.order_transactions.glue.register_tables",
                fromlist=["register_all"],
            ).register_all(),
        )

    # DAG flow
    wait_for_customer_master >> ingest_group >> quality_bronze_group >> transform_group >> quality_gold_group >> register_group
