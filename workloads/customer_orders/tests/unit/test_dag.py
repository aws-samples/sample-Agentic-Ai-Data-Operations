import re
from pathlib import Path

import yaml

from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DAG_PATH = ROOT / "dags" / "customer_orders_dag.py"


def test_schedule_spec_preserves_authoritative_schedule_and_failure_policy():
    spec, spec_hash = load_spec(CONFIG / "schedule.yaml", "dag", "v2")

    assert spec_hash
    assert spec["dataset_name"] == "customer_orders"
    assert spec["dag_id"] == "customer_orders_daily"
    assert spec["schema_version"] == "v2"
    assert spec["schedule"] == {
        "cron": "0 9 * * *",
        "timezone": "America/New_York",
        "catchup": False,
        "max_active_runs": 1,
        "start_date": "2026-01-01",
    }
    assert spec["retries"] == {
        "count": 3,
        "delay_seconds": 300,
        "backoff": True,
        "max_delay_seconds": 3600,
    }
    assert spec["failure_handling"]["on_failure_callback"] == "sns_alert"
    assert spec["failure_handling"]["notification_channel"] == "customer_orders_alerts"
    assert spec["sla"]["deadline_minutes"] == 15


def test_task_chain_matches_bronze_to_gold_order():
    spec, _ = load_spec(CONFIG / "schedule.yaml", "dag", "v2")
    tasks = spec["tasks"]

    assert [task["task_id"] for task in tasks] == [
        "ingest_bronze",
        "transform_bronze_to_silver",
        "quality_check_silver",
        "transform_silver_to_gold",
        "quality_check_gold",
    ]
    assert [task.get("depends_on", []) for task in tasks] == [
        [],
        ["ingest_bronze"],
        ["transform_bronze_to_silver"],
        ["quality_check_silver"],
        ["transform_silver_to_gold"],
    ]
    assert tasks[1]["params"]["--CUSTOMER_ORDERS_TOKEN_SECRET_ID"].startswith("${")
    assert tasks[0]["params"] == {
        "--CUSTOMER_ORDERS_SOURCE_URI": "${CUSTOMER_ORDERS_SOURCE_URI}",
        "--DATA_LAKE_BUCKET": "${DATA_LAKE_BUCKET}",
    }
    assert "customer_orders_db.silver_customer_orders" in yaml.safe_dump(tasks[2])
    assert "customer_orders_db.gold_customer_orders" in yaml.safe_dump(tasks[4])


def test_rendered_dag_has_provenance_and_no_infrastructure_literals():
    content = DAG_PATH.read_text()
    header = content.splitlines()[:5]

    assert len(header) == 5
    assert "spec_hash:" in header[0]
    assert "template_id: airflow_dag" in header[1]
    assert "template_hash:" in header[2]
    assert "schema_version: v2" in header[3]
    assert "rendered_at: 2026-10-22T18:18:44Z" in header[4]
    assert "arn:aws:" not in content
    assert not re.search(r"\b\d{12}\b", content)  # no AWS account IDs
    assert "customer_orders_alerts" in content
    assert 'Variable.get("CUSTOMER_ORDERS_SOURCE_URI", default_var="")' in content
    assert 'Variable.get("DATA_LAKE_BUCKET", default_var="")' in content
    assert 'Variable.get("CUSTOMER_ORDERS_QUARANTINE_URI", default_var="")' in content
    assert 'Variable.get("CUSTOMER_ORDERS_TOKEN_SECRET_ID", default_var="")' in content
    assert '"--ADOP_RUN_ID": "{{ run_id }}"' in content
    assert '"${CUSTOMER_ORDERS_SOURCE_URI}"' not in content
    assert '"${DATA_LAKE_BUCKET}"' not in content
    assert '"${CUSTOMER_ORDERS_QUARANTINE_URI}"' not in content
    assert '"${CUSTOMER_ORDERS_TOKEN_SECRET_ID}"' not in content
    assert "America/New_York" in content
    assert "start_date=pendulum.datetime" in content
