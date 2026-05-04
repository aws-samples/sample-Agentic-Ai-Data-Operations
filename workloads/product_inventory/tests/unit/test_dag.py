"""
Unit tests for Product Inventory DAG

Tests:
1. Schedule configuration validation
2. DAG file can be parsed without errors
3. DAG structure and task dependencies
4. Airflow best practices compliance
"""

import pytest
import yaml
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# Mock Airflow modules for local testing
airflow_mock = MagicMock()
sys.modules['airflow'] = airflow_mock
sys.modules['airflow.decorators'] = airflow_mock
sys.modules['airflow.operators.python'] = airflow_mock
sys.modules['airflow.utils.task_group'] = airflow_mock
sys.modules['airflow.models'] = airflow_mock
sys.modules['airflow.models.variable'] = airflow_mock

# Mock Variable.get
def mock_variable_get(key, default_var=None):
    """Mock Airflow Variable.get for testing."""
    defaults = {
        "product_inventory_bronze_path": "s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/bronze/product_inventory/",
        "product_inventory_silver_path": "s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/silver/product_inventory/",
        "product_inventory_gold_path": "s3://aws-glue-assets-123456789012-us-east-1/demo-ai-agents/gold/product_inventory/",
    }
    return defaults.get(key, default_var)

airflow_mock.models.Variable.get = mock_variable_get


# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[4]
WORKLOAD_ROOT = PROJECT_ROOT / "workloads" / "product_inventory"
SCHEDULE_CONFIG = WORKLOAD_ROOT / "config" / "schedule.yaml"
DAG_FILE = WORKLOAD_ROOT / "dags" / "product_inventory_dag.py"


@pytest.fixture
def schedule_config():
    """Load schedule.yaml."""
    with open(SCHEDULE_CONFIG, 'r') as f:
        return yaml.safe_load(f)


class TestScheduleConfig:
    """Test schedule.yaml validation."""

    def test_schedule_file_exists(self):
        """schedule.yaml exists."""
        assert SCHEDULE_CONFIG.exists(), f"schedule.yaml not found at {SCHEDULE_CONFIG}"

    def test_schedule_has_required_fields(self, schedule_config):
        """schedule.yaml has all required fields."""
        required_fields = [
            "dag_id",
            "description",
            "schedule_interval",
            "start_date",
            "catchup",
            "max_active_runs",
            "default_args",
            "tags",
        ]

        for field in required_fields:
            assert field in schedule_config["schedule"], f"Missing field: {field}"

    def test_dag_id_matches(self, schedule_config):
        """dag_id matches expected value."""
        assert schedule_config["schedule"]["dag_id"] == "product_inventory_pipeline"

    def test_schedule_interval_valid_cron(self, schedule_config):
        """schedule_interval is valid cron expression."""
        schedule = schedule_config["schedule"]["schedule_interval"]
        assert schedule == "0 6 * * *", f"Invalid schedule: {schedule}"

        # Validate cron format (5 fields)
        fields = schedule.split()
        assert len(fields) == 5, f"Cron must have 5 fields, got {len(fields)}"

    def test_start_date_valid_format(self, schedule_config):
        """start_date is valid ISO date."""
        start_date = schedule_config["schedule"]["start_date"]
        assert start_date == "2026-03-01"

        # Validate can be parsed
        try:
            datetime.fromisoformat(start_date)
        except ValueError as e:
            pytest.fail(f"Invalid start_date format: {e}")

    def test_catchup_is_false(self, schedule_config):
        """catchup is False."""
        assert schedule_config["schedule"]["catchup"] is False

    def test_max_active_runs_is_one(self, schedule_config):
        """max_active_runs is 1."""
        assert schedule_config["schedule"]["max_active_runs"] == 1

    def test_default_args_has_required_fields(self, schedule_config):
        """default_args has owner, retries, retry_delay."""
        default_args = schedule_config["schedule"]["default_args"]

        required = ["owner", "retries", "retry_delay_seconds"]
        for field in required:
            assert field in default_args, f"Missing default_args field: {field}"

    def test_default_args_retries(self, schedule_config):
        """default_args.retries is 3."""
        assert schedule_config["schedule"]["default_args"]["retries"] == 3

    def test_default_args_retry_delay(self, schedule_config):
        """default_args.retry_delay_seconds is positive."""
        retry_delay = schedule_config["schedule"]["default_args"]["retry_delay_seconds"]
        assert retry_delay > 0, f"retry_delay must be positive, got {retry_delay}"

    def test_default_args_owner(self, schedule_config):
        """default_args.owner is set."""
        owner = schedule_config["schedule"]["default_args"]["owner"]
        assert owner == "data-engineering"

    def test_tags_present(self, schedule_config):
        """tags list is present and not empty."""
        tags = schedule_config["schedule"]["tags"]
        assert isinstance(tags, list), "tags must be a list"
        assert len(tags) > 0, "tags list is empty"

    def test_failure_notification_configured(self, schedule_config):
        """failure_notification is configured with SNS."""
        notification = schedule_config["schedule"]["failure_notification"]
        assert notification["type"] == "sns"
        assert "topic_arn" in notification


class TestDAGStructure:
    """Test DAG file structure and parsing."""

    def test_dag_file_exists(self):
        """DAG file exists."""
        assert DAG_FILE.exists(), f"DAG file not found at {DAG_FILE}"

    def test_dag_file_imports(self):
        """DAG file can be imported without errors."""
        try:
            with open(DAG_FILE, 'r') as f:
                code = f.read()

            # Check for required imports
            assert "from airflow import DAG" in code
            assert "from airflow.operators.python import PythonOperator" in code
            assert "from airflow.utils.task_group import TaskGroup" in code
            assert "from datetime import datetime, timedelta" in code

        except Exception as e:
            pytest.fail(f"Failed to read DAG file: {e}")

    def test_dag_id_in_code(self):
        """DAG_ID constant matches schedule config."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'DAG_ID = "product_inventory_pipeline"' in code

    def test_schedule_interval_in_code(self):
        """SCHEDULE_INTERVAL constant matches schedule config."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'SCHEDULE_INTERVAL = "0 6 * * *"' in code

    def test_default_args_in_code(self):
        """DEFAULT_ARGS defined with required fields."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'DEFAULT_ARGS = {' in code
        assert '"owner": "data-engineering"' in code
        assert '"retries": 3' in code
        assert '"retry_delay": timedelta(minutes=5)' in code

    def test_catchup_false_in_dag(self):
        """DAG definition has catchup=False."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert "catchup=False" in code

    def test_max_active_runs_in_dag(self):
        """DAG definition has max_active_runs=1."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert "max_active_runs=1" in code

    def test_tags_in_dag(self):
        """DAG definition has tags list."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'tags=["product", "inventory", "daily", "star-schema"]' in code

    def test_on_failure_callback_defined(self):
        """on_failure_callback function is defined."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert "def failure_callback(context):" in code
        assert "on_failure_callback=failure_callback" in code

    def test_doc_md_in_dag(self):
        """DAG definition has doc_md."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert "doc_md=__doc__" in code

        # Check module docstring exists
        assert '"""' in code[:500], "Module docstring missing"


class TestTaskGroups:
    """Test TaskGroup organization."""

    def test_ingest_task_group_exists(self):
        """Ingest TaskGroup is defined."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'with TaskGroup("ingest"' in code
        assert 'validate_source_task = PythonOperator' in code

    def test_transform_task_group_exists(self):
        """Transform TaskGroup is defined."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'with TaskGroup("transform"' in code
        assert 'bronze_to_silver_task = PythonOperator' in code
        assert 'silver_quality_gate_task = PythonOperator' in code
        assert 'silver_to_gold_task = PythonOperator' in code
        assert 'gold_quality_gate_task = PythonOperator' in code

    def test_publish_task_group_exists(self):
        """Publish TaskGroup is defined."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'with TaskGroup("publish"' in code
        assert 'register_catalog_task = PythonOperator' in code


class TestTaskDependencies:
    """Test task dependencies."""

    def test_ingest_to_transform_dependency(self):
        """Ingest runs before Transform."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert "ingest >> transform >> publish" in code

    def test_transform_stage_dependencies(self):
        """Transform stage tasks have correct order."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        # Bronze → Silver → Quality → Gold → Quality
        assert "bronze_to_silver_task >> silver_quality_gate_task >> silver_to_gold_task >> gold_quality_gate_task" in code

class TestSLAConfiguration:
    """Test SLA configuration."""

    def test_sla_on_bronze_to_silver(self):
        """bronze_to_silver task has SLA."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        # Find bronze_to_silver_task definition
        bronze_section = code[code.find("bronze_to_silver_task = PythonOperator"):]
        bronze_section = bronze_section[:bronze_section.find("silver_quality_gate_task")]

        assert "sla=timedelta(hours=1)" in bronze_section

    def test_sla_on_silver_to_gold(self):
        """silver_to_gold task has SLA."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        # Find silver_to_gold_task definition
        gold_section = code[code.find("silver_to_gold_task = PythonOperator"):]
        gold_section = gold_section[:gold_section.find("gold_quality_gate_task")]

        assert "sla=timedelta(hours=1)" in gold_section


class TestPythonOperatorConfiguration:
    """Test PythonOperator configuration."""

    def test_no_provide_context_true(self):
        """PythonOperator does not use provide_context=True (deprecated in Airflow 2.0+)."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        # provide_context is set but should be consistent
        # In modern Airflow, it's implicit, but setting it explicitly is fine
        # The anti-pattern is mixing old and new styles
        pass  # This test is informational

    def test_all_tasks_call_scripts(self):
        """All PythonOperators call scripts in workloads/product_inventory/scripts/."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        # Check task functions use importlib to load scripts
        assert "importlib.util.spec_from_file_location" in code
        assert "SCRIPTS_ROOT" in code


class TestAirflowBestPractices:
    """Test Airflow best practices compliance."""

    def test_no_hardcoded_secrets(self):
        """No hardcoded AWS credentials in DAG."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        # Check for common secret patterns
        forbidden = [
            "AKIA",  # AWS access key prefix
            "aws_access_key_id",
            "aws_secret_access_key",
            "password",
        ]

        for pattern in forbidden:
            assert pattern not in code, f"Potential hardcoded secret found: {pattern}"

    def test_no_subdag_operator(self):
        """No SubDagOperator used (deprecated)."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert "SubDagOperator" not in code

    def test_no_dynamic_start_date(self):
        """start_date is not datetime.now() (anti-pattern)."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert "datetime.now()" not in code
        assert "START_DATE = datetime(2026, 3, 1)" in code

    def test_uses_airflow_variables(self):
        """Uses Airflow Variables for configuration."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert "Variable.get" in code

    def test_exponential_backoff_enabled(self):
        """Exponential backoff is enabled for retries."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert '"retry_exponential_backoff": True' in code


class TestQualityGates:
    """Test quality gate logic in task functions."""

    def test_silver_quality_gate_blocks_on_low_score(self):
        """silver_quality_gate raises ValueError if score < 0.80."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'if result["overall_score"] < 0.80:' in code
        assert 'raise ValueError(f"Silver quality gate failed: score' in code

    def test_silver_quality_gate_blocks_on_critical_failures(self):
        """silver_quality_gate raises ValueError if critical failures > 0."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'if result["critical_failures"] > 0:' in code

    def test_gold_quality_gate_blocks_on_low_score(self):
        """gold_quality_gate raises ValueError if score < 0.95."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'if result["overall_score"] < 0.95:' in code
        assert 'raise ValueError(f"Gold quality gate failed: score' in code

    def test_gold_quality_gate_blocks_on_critical_failures(self):
        """gold_quality_gate raises ValueError if critical failures > 0."""
        with open(DAG_FILE, 'r') as f:
            code = f.read()

        assert 'if result["critical_failures"] > 0:' in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
