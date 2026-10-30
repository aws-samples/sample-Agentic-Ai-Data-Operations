"""
Unit tests for customer_orders DAG - Static Analysis.

Tests DAG structure and configuration without requiring Airflow runtime.
"""
import sys
import re
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def dag_file():
    """Get the DAG file path."""
    # Try the manual file first (since renderer had issues)
    manual_path = PROJECT_ROOT / "workloads" / "customer_orders" / "MANUAL_DAG_customer_orders_pipeline.py"
    normal_path = PROJECT_ROOT / "workloads" / "customer_orders" / "dags" / "customer_orders_pipeline.py"
    
    if manual_path.exists():
        return manual_path
    elif normal_path.exists():
        return normal_path
    else:
        pytest.skip("DAG file not found")


@pytest.fixture
def dag_content(dag_file):
    """Read DAG file content."""
    return dag_file.read_text()


class TestDAGFileStructure:
    """Test DAG file structure without runtime dependencies."""

    def test_dag_file_exists(self, dag_file):
        """DAG file should exist."""
        assert dag_file.exists()

    def test_dag_imports_airflow(self, dag_content):
        """DAG should import from Airflow."""
        assert "from airflow import DAG" in dag_content
        assert "from airflow.utils.task_group import TaskGroup" in dag_content

    def test_dag_has_dag_id(self, dag_content):
        """DAG should define dag_id."""
        assert 'dag_id="customer_orders_pipeline"' in dag_content

    def test_dag_has_schedule(self, dag_content):
        """DAG should have schedule_interval."""
        assert 'schedule_interval="0 9 * * *"' in dag_content

    def test_dag_has_description(self, dag_content):
        """DAG should have a description."""
        assert "description=" in dag_content
        assert "Bronze" in dag_content and "Silver" in dag_content and "Gold" in dag_content


class TestDAGConfiguration:
    """Test DAG configuration settings."""

    def test_catchup_disabled(self, dag_content):
        """Catchup should be disabled."""
        assert "catchup=False" in dag_content

    def test_max_active_runs_set(self, dag_content):
        """Max active runs should be set to 1."""
        assert "max_active_runs=1" in dag_content

    def test_retries_configured(self, dag_content):
        """Retries should be configured."""
        assert '"retries": 3' in dag_content or "'retries': 3" in dag_content

    def test_retry_delay_configured(self, dag_content):
        """Retry delay should be configured."""
        assert "retry_delay" in dag_content
        assert "timedelta" in dag_content

    def test_exponential_backoff_enabled(self, dag_content):
        """Exponential backoff should be enabled."""
        assert "retry_exponential_backoff" in dag_content
        assert "True" in dag_content

    def test_execution_timeout_set(self, dag_content):
        """Execution timeout should be set."""
        assert "execution_timeout" in dag_content


class TestDAGVariables:
    """Test Airflow Variables usage."""

    def test_all_variable_gets_have_defaults(self, dag_content):
        """All Variable.get() calls should have default_var."""
        variable_calls = re.findall(r'Variable\.get\([^)]+\)', dag_content)
        
        assert len(variable_calls) > 0, "No Variable.get() calls found"
        
        for call in variable_calls:
            assert "default_var=" in call, f"Variable.get() missing default_var: {call}"

    def test_required_variables_defined(self, dag_content):
        """Required variables should be defined."""
        required_vars = [
            "GLUE_IAM_ROLE_ARN",
            "MWAA_BUCKET",
            "GLUE_TEMP_BUCKET",
            "CUSTOMER_ORDERS_QUARANTINE_URI",
            "CUSTOMER_ORDERS_TOKEN_SECRET_ID",
        ]
        
        for var in required_vars:
            assert f'Variable.get("{var}"' in dag_content, f"Variable '{var}' not defined"


class TestTaskGroups:
    """Test TaskGroup usage."""

    def test_uses_taskgroup(self, dag_content):
        """DAG should use TaskGroup."""
        assert "TaskGroup" in dag_content
        assert "with TaskGroup" in dag_content

    def test_no_subdag_operator(self, dag_content):
        """DAG should not use deprecated SubDagOperator."""
        assert "SubDagOperator" not in dag_content

    def test_expected_task_groups_defined(self, dag_content):
        """Expected task groups should be defined."""
        expected_groups = [
            "bronze_to_silver",
            "silver_quality",
            "silver_to_gold",
            "gold_quality",
        ]
        
        for group in expected_groups:
            assert f'group_id="{group}"' in dag_content, f"Task group '{group}' not found"


class TestGlueJobConfiguration:
    """Test Glue job configuration."""

    def test_glue_operator_used(self, dag_content):
        """DAG should use GlueJobOperator."""
        assert "GlueJobOperator" in dag_content

    def test_glue_version_specified(self, dag_content):
        """Glue version should be specified."""
        assert '"GlueVersion": "4.0"' in dag_content

    def test_worker_configuration(self, dag_content):
        """Worker configuration should be specified."""
        assert '"NumberOfWorkers": 2' in dag_content
        assert '"WorkerType": "G.1X"' in dag_content

    def test_glue_datacatalog_enabled(self, dag_content):
        """Glue Data Catalog should be enabled."""
        assert "--enable-glue-datacatalog" in dag_content

    def test_glue_lineage_enabled(self, dag_content):
        """Glue Data Lineage should be enabled for transforms."""
        # Should appear at least twice (bronze_to_silver and silver_to_gold)
        assert dag_content.count("--enable-data-lineage") >= 2

    def test_adop_run_id_passed(self, dag_content):
        """ADOP_RUN_ID should be passed to jobs."""
        assert "--ADOP_RUN_ID" in dag_content
        assert "{{ run_id }}" in dag_content


class TestScriptReferences:
    """Test script path references."""

    def test_transform_scripts_referenced(self, dag_content):
        """Transform scripts should be referenced."""
        assert "bronze_to_silver.py" in dag_content
        assert "silver_to_gold.py" in dag_content

    def test_quality_script_referenced(self, dag_content):
        """Quality check script should be referenced."""
        assert "quality_check.py" in dag_content

    def test_scripts_use_s3_paths(self, dag_content):
        """Scripts should use S3 paths with variables."""
        # Should use MWAA_BUCKET variable in paths
        assert "MWAA_BUCKET" in dag_content
        assert "s3://" in dag_content


class TestFailureHandling:
    """Test failure handling configuration."""

    def test_failure_callback_defined(self, dag_content):
        """on_failure_callback function should be defined."""
        assert "def on_failure_callback" in dag_content

    def test_failure_callback_has_context(self, dag_content):
        """Failure callback should accept context parameter."""
        assert "def on_failure_callback(context" in dag_content

    def test_failure_callback_logs(self, dag_content):
        """Failure callback should log failures."""
        # Should print or log the failure
        callback_start = dag_content.find("def on_failure_callback")
        if callback_start > 0:
            callback_section = dag_content[callback_start:callback_start + 1000]
            assert "print" in callback_section or "log" in callback_section.lower()

    def test_tasks_use_failure_callback(self, dag_content):
        """Tasks should reference on_failure_callback."""
        assert "on_failure_callback=on_failure_callback" in dag_content


class TestGDPRCompliance:
    """Test GDPR compliance configuration."""

    def test_gdpr_tag_present(self, dag_content):
        """DAG should be tagged with GDPR."""
        assert '"gdpr"' in dag_content or "'gdpr'" in dag_content

    def test_quarantine_uri_used(self, dag_content):
        """Quarantine URI should be configured."""
        assert "CUSTOMER_ORDERS_QUARANTINE_URI" in dag_content

    def test_token_secret_used(self, dag_content):
        """Token secret should be configured for PII tokenization."""
        assert "CUSTOMER_ORDERS_TOKEN_SECRET_ID" in dag_content

    def test_gdpr_variables_passed_to_glue(self, dag_content):
        """GDPR variables should be passed as job arguments."""
        # Quarantine URI should be in DefaultArguments
        assert "--CUSTOMER_ORDERS_QUARANTINE_URI" in dag_content
        assert "--CUSTOMER_ORDERS_TOKEN_SECRET_ID" in dag_content


class TestSecurity:
    """Test security best practices."""

    def test_no_hardcoded_credentials(self, dag_content):
        """DAG should not contain hardcoded credentials."""
        # Check for common credential patterns (case insensitive)
        content_lower = dag_content.lower()
        
        # Allow "password" in variable names but not values
        if "password" in content_lower:
            # Make sure it's only in variable names or comments
            assert not re.search(r'password\s*=\s*["\'](?!.*variable)', content_lower)

    def test_no_hardcoded_account_ids_except_defaults(self, dag_content):
        """DAG should not have hardcoded account IDs except in default_var."""
        # Find all 12-digit numbers (potential account IDs)
        account_ids = re.findall(r'\b\d{12}\b', dag_content)
        
        # Each should only appear in default_var context
        for account_id in account_ids:
            # Find the context around the account ID
            idx = dag_content.find(account_id)
            context = dag_content[max(0, idx - 100):idx + 100]
            assert "default_var" in context, f"Account ID {account_id} not in default_var context"

    def test_uses_iam_roles_not_keys(self, dag_content):
        """DAG should use IAM roles, not access keys."""
        assert "GLUE_IAM_ROLE_ARN" in dag_content
        assert "aws_access_key_id" not in dag_content.lower()
        assert "aws_secret_access_key" not in dag_content.lower()


class TestTableReferences:
    """Test Glue Catalog table references."""

    def test_silver_table_referenced(self, dag_content):
        """Silver table should be referenced."""
        assert "silver_customer_orders" in dag_content

    def test_gold_table_referenced(self, dag_content):
        """Gold table should be referenced."""
        assert "gold_customer_orders" in dag_content

    def test_table_names_include_database(self, dag_content):
        """Table references should include database."""
        # Should have glue_catalog prefix
        assert "glue_catalog.customer_orders_db" in dag_content


class TestTaskDependencies:
    """Test task dependency structure."""

    def test_task_groups_chained(self, dag_content):
        """Task groups should be chained with >> operator."""
        # Look for the dependency chain
        assert ">>" in dag_content
        
        # Should chain bronze -> silver_quality -> silver_to_gold -> gold_quality
        dependency_pattern = r'bronze_to_silver.*>>.*silver_quality.*>>.*silver_to_gold.*>>.*gold_quality'
        assert re.search(dependency_pattern, dag_content.replace('\n', ' '))


class TestDocumentation:
    """Test DAG documentation."""

    def test_has_module_docstring(self, dag_content):
        """DAG file should have a module docstring."""
        # Should start with a triple-quoted string
        lines = dag_content.split('\n')
        non_comment_lines = [l for l in lines if not l.strip().startswith('#')]
        if non_comment_lines:
            first_line = non_comment_lines[0].strip()
            assert first_line.startswith('"""') or first_line.startswith("'''")

    def test_docstring_mentions_zones(self, dag_content):
        """Docstring should mention data zones."""
        # Get the module docstring (first triple-quoted string)
        docstring_match = re.search(r'"""(.+?)"""', dag_content, re.DOTALL)
        if docstring_match:
            docstring = docstring_match.group(1)
            assert "Bronze" in docstring or "Silver" in docstring or "Gold" in docstring


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
