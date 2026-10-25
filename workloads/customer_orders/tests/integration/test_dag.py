import ast
import re
from pathlib import Path

from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DAG_PATH = ROOT / "dags" / "customer_orders_dag.py"


def test_rendered_dag_compiles_and_contains_exactly_one_dag_context():
    source = DAG_PATH.read_text()
    tree = ast.parse(source, filename=str(DAG_PATH))

    compile(source, str(DAG_PATH), "exec")
    dag_contexts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DAG"
    ]
    assert len(dag_contexts) == 1
    assert "DAG_ID = \"customer_orders_daily\"" in source


def test_rendered_dag_links_existing_transform_and_quality_artifacts():
    spec, _ = load_spec(CONFIG / "schedule.yaml", "dag", "v2")
    source = DAG_PATH.read_text()
    rendered_files = {
        "scripts/transform/bronze_to_silver.py",
        "scripts/transform/silver_to_gold.py",
        "scripts/quality/quality_check.py",
    }

    for task in spec["tasks"][1:]:
        if task["type"] in {"glue_job", "quality_check"}:
            assert task["script_path"] in rendered_files
            assert Path(ROOT / task["script_path"]).exists()
            assert Path(task["script_path"]).name in source


def test_rendered_dag_preserves_retry_alert_sla_and_chain():
    source = DAG_PATH.read_text()

    assert '"retries": 3' in source
    assert "retry_exponential_backoff" in source
    assert "def _notify_failure(context):" in source
    assert '"on_failure_callback": _notify_failure' in source
    assert "dagrun_timeout=timedelta(minutes=15)" in source
    assert "catchup=False" in source
    assert "max_active_runs=1" in source
    assert 'tz="America/New_York"' in source
    assert 'Variable.get("CUSTOMER_ORDERS_SOURCE_URI", default_var="")' in source
    assert 'Variable.get("DATA_LAKE_BUCKET", default_var="")' in source
    assert 'Variable.get("CUSTOMER_ORDERS_QUARANTINE_URI", default_var="")' in source
    assert 'Variable.get("CUSTOMER_ORDERS_TOKEN_SECRET_ID", default_var="")' in source
    assert '"--ADOP_RUN_ID": "{{ run_id }}"' in source
    for upstream, downstream in [
        ("ingest_bronze", "transform_bronze_to_silver"),
        ("transform_bronze_to_silver", "quality_check_silver"),
        ("quality_check_silver", "transform_silver_to_gold"),
        ("transform_silver_to_gold", "quality_check_gold"),
    ]:
        assert re.search(rf"\b{upstream}\s+>>\s+{downstream}", source)
