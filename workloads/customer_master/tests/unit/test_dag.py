"""Unit tests for customer_master_dag.py structure and configuration."""

import os
import ast

import pytest

DAG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "dags", "customer_master_dag.py"
)


@pytest.fixture
def dag_source():
    """Read DAG file source code."""
    with open(DAG_PATH, "r") as f:
        return f.read()


@pytest.fixture
def dag_ast(dag_source):
    """Parse DAG AST."""
    return ast.parse(dag_source)


class TestDagStructure:
    def test_dag_file_exists(self):
        assert os.path.isfile(DAG_PATH)

    def test_dag_id_present(self, dag_source):
        assert "customer_master_pipeline" in dag_source

    def test_schedule_defined(self, dag_source):
        assert "0 6 * * *" in dag_source

    def test_catchup_false(self, dag_source):
        assert "catchup=False" in dag_source

    def test_max_active_runs_1(self, dag_source):
        assert "max_active_runs=1" in dag_source

    def test_retries_3(self, dag_source):
        assert '"retries": 3' in dag_source

    def test_exponential_backoff(self, dag_source):
        assert "retry_exponential_backoff" in dag_source

    def test_has_doc_md(self, dag_source):
        assert "doc_md" in dag_source

    def test_has_sla(self, dag_source):
        assert "sla=" in dag_source

    def test_uses_task_groups(self, dag_source):
        assert "TaskGroup" in dag_source

    def test_no_subdagoperator(self, dag_source):
        assert "SubDagOperator" not in dag_source

    def test_no_hardcoded_secrets(self, dag_source):
        # No AWS keys, passwords, tokens
        for pattern in ["AKIA", "aws_secret", "password=", "token="]:
            assert pattern not in dag_source

    def test_no_provide_context(self, dag_source):
        assert "provide_context" not in dag_source

    def test_no_datetime_now_start(self, dag_source):
        assert "datetime.now()" not in dag_source

    def test_has_tags(self, dag_source):
        assert "tags=" in dag_source

    def test_python_operator_used(self, dag_source):
        assert "PythonOperator" in dag_source


class TestDagTasks:
    def test_has_ingest_task(self, dag_source):
        assert "ingest_to_bronze" in dag_source

    def test_has_bronze_quality(self, dag_source):
        assert "bronze_quality_check" in dag_source

    def test_has_transform_task(self, dag_source):
        assert "transform_bronze_to_gold" in dag_source

    def test_has_gold_quality(self, dag_source):
        assert "gold_quality_check" in dag_source

    def test_has_register_task(self, dag_source):
        assert "register_glue_tables" in dag_source

    def test_task_groups_defined(self, dag_source):
        assert "bronze_stage" in dag_source
        assert "gold_stage" in dag_source
        assert "catalog_stage" in dag_source

    def test_task_dependency_chain(self, dag_source):
        assert "bronze_stage >> gold_stage >> catalog_stage" in dag_source


class TestDagDefaultArgs:
    def test_owner_set(self, dag_source):
        assert '"owner": "crm-team"' in dag_source

    def test_depends_on_past_false(self, dag_source):
        assert '"depends_on_past": False' in dag_source

    def test_email_on_failure(self, dag_source):
        assert '"email_on_failure": True' in dag_source


class TestDagCallables:
    def test_ingest_callable(self, dag_source):
        assert "def _ingest(" in dag_source

    def test_check_bronze_callable(self, dag_source):
        assert "def _check_bronze(" in dag_source

    def test_transform_callable(self, dag_source):
        assert "def _transform(" in dag_source

    def test_check_gold_callable(self, dag_source):
        assert "def _check_gold(" in dag_source

    def test_register_callable(self, dag_source):
        assert "def _register_glue(" in dag_source

    def test_quality_gate_raises_on_failure(self, dag_source):
        # Both quality check callables should raise on failure
        assert "raise ValueError" in dag_source
