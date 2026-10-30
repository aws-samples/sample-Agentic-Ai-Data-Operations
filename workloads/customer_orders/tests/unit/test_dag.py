"""Unit tests for customer_orders DAG — syntax and structure validation.

These tests operate entirely on the rendered DAG source text (no Airflow import,
no AWS calls).  They pass or fail deterministically, making them the primary gate
in the run_pytest_gate call.

Scope:
  - File existence and parseable Python syntax
  - Airflow best-practice constants (catchup=False, max_active_runs, retries)
  - Security: no hardcoded secrets / bucket paths / account IDs
  - All Variable.get() calls carry default_var
  - Task IDs and dependency wiring
  - SLA / dagrun_timeout
  - Codegen header (spec_hash, template_id, rendered_at)
  - GDPR/compliance tags
"""

import ast
import re
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
TEST_FILE = Path(__file__).resolve()
# test_dag.py → unit → tests → customer_orders → workloads → project_root
WORKLOAD_DIR = TEST_FILE.parent.parent.parent          # workloads/customer_orders
PROJECT_ROOT = WORKLOAD_DIR.parent.parent              # repo root
DAG_FILE = WORKLOAD_DIR / "dags" / "customer_orders_pipeline.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content() -> str:
    """Return DAG file content, caching per test run."""
    return DAG_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existence & parse
# ---------------------------------------------------------------------------

class TestFileExistenceAndParsing:

    def test_dag_file_exists(self):
        assert DAG_FILE.exists(), f"DAG file not found: {DAG_FILE}"

    def test_dag_parses_as_valid_python(self):
        content = _content()
        try:
            ast.parse(content)
        except SyntaxError as exc:
            pytest.fail(f"DAG file has syntax errors: {exc}")

    def test_codegen_header_present(self):
        """Renderer must prefix every artifact with 5 comment lines."""
        lines = _content().split("\n")
        assert lines[0].startswith("# spec_hash:"), \
            f"Line 0 should be '# spec_hash:…', got: {lines[0]!r}"
        assert lines[1].startswith("# template_id:"), \
            f"Line 1 should be '# template_id:…', got: {lines[1]!r}"
        assert lines[2].startswith("# template_hash:"), \
            f"Line 2 should be '# template_hash:…', got: {lines[2]!r}"
        assert lines[3].startswith("# schema_version:"), \
            f"Line 3 should be '# schema_version:…', got: {lines[3]!r}"
        assert lines[4].startswith("# rendered_at:"), \
            f"Line 4 should be '# rendered_at:…', got: {lines[4]!r}"

    def test_template_id_is_airflow_dag(self):
        match = re.search(r"# template_id:\s*(\S+)", _content())
        assert match, "template_id not found in header"
        assert match.group(1) == "airflow_dag", \
            f"Expected template_id=airflow_dag, got {match.group(1)}"


# ---------------------------------------------------------------------------
# DAG-level configuration
# ---------------------------------------------------------------------------

class TestDagConfiguration:

    def test_dag_id_constant(self):
        match = re.search(r'DAG_ID\s*=\s*"([^"]+)"', _content())
        assert match, "DAG_ID constant not found"
        assert match.group(1) == "customer_orders_pipeline", \
            f"DAG_ID wrong: {match.group(1)}"

    def test_schedule_interval(self):
        match = re.search(r'schedule_interval\s*=\s*"([^"]+)"', _content())
        assert match, "schedule_interval not found (expected quoted cron string)"
        assert match.group(1) == "0 9 * * *", \
            f"schedule_interval wrong: {match.group(1)!r}"

    def test_timezone_is_america_new_york(self):
        match = re.search(r'tz\s*=\s*"([^"]+)"', _content())
        assert match, "tz= not found in DAG start_date"
        assert match.group(1) == "America/New_York", \
            f"timezone wrong: {match.group(1)!r}"

    def test_catchup_is_false(self):
        match = re.search(r'catchup\s*=\s*(False|True)', _content())
        assert match, "catchup= not found"
        assert match.group(1) == "False", "catchup must be False"

    def test_max_active_runs_is_one(self):
        match = re.search(r'max_active_runs\s*=\s*(\d+)', _content())
        assert match, "max_active_runs not found"
        assert int(match.group(1)) == 1, \
            f"max_active_runs must be 1, got {match.group(1)}"

    def test_dagrun_timeout_180_minutes(self):
        match = re.search(r'dagrun_timeout\s*=\s*timedelta\(minutes=(\d+)\)', _content())
        assert match, "dagrun_timeout not found"
        assert int(match.group(1)) == 180, \
            f"dagrun_timeout must be 180 min, got {match.group(1)}"

    def test_dag_description_mentions_all_three_zones(self):
        match = re.search(r'description\s*=\s*"([^"]+)"', _content())
        assert match, "description not found"
        desc = match.group(1)
        for zone in ("Bronze", "Silver", "Gold"):
            assert zone in desc, f"description missing '{zone}': {desc!r}"

    def test_dag_tags(self):
        match = re.search(r'tags\s*=\s*(\[[^\]]+\])', _content())
        assert match, "tags not found"
        tags_str = match.group(1)
        for expected_tag in ('"customer_orders"', '"gdpr"', '"daily"', '"bronze_silver_gold"'):
            assert expected_tag in tags_str, \
                f"Tag {expected_tag} missing from tags list: {tags_str}"


# ---------------------------------------------------------------------------
# default_args / retry configuration
# ---------------------------------------------------------------------------

class TestDefaultArgs:

    def test_retries_is_three(self):
        # Match "retries": 3 inside default_args dict
        match = re.search(r'"retries"\s*:\s*(\d+)', _content())
        assert match, '"retries" not found in default_args'
        assert int(match.group(1)) == 3, \
            f'"retries" must be 3, got {match.group(1)}'

    def test_retry_delay_300_seconds(self):
        match = re.search(r'"retry_delay"\s*:\s*timedelta\(seconds=(\d+)\)', _content())
        assert match, '"retry_delay" not found in default_args'
        assert int(match.group(1)) == 300, \
            f'"retry_delay" must be 300 s, got {match.group(1)}'

    def test_exponential_backoff_enabled(self):
        match = re.search(r'"retry_exponential_backoff"\s*:\s*(True|False)', _content())
        assert match, '"retry_exponential_backoff" not found'
        assert match.group(1) == "True", \
            '"retry_exponential_backoff" must be True'

    def test_on_failure_callback_defined_and_referenced(self):
        content = _content()
        assert "def _notify_failure(context):" in content, \
            "_notify_failure callback not defined"
        assert '"on_failure_callback": _notify_failure' in content, \
            "_notify_failure not referenced in default_args"


# ---------------------------------------------------------------------------
# Security: no hardcoded infrastructure values
# ---------------------------------------------------------------------------

class TestSecurity:

    def test_no_hardcoded_aws_account_ids(self):
        """ARN patterns should not contain literal 12-digit account IDs."""
        content = _content()
        matches = re.findall(r'arn:aws:[^:]*::[0-9]{12}', content)
        # Filter out any that are inside Jinja template placeholders (won't appear in rendered output anyway)
        assert not matches, \
            f"Hardcoded AWS account IDs found: {matches}"

    def test_no_hardcoded_s3_paths(self):
        """Literal s3:// paths must not appear outside Variable.get() or template placeholders."""
        content = _content()
        for line in content.split("\n"):
            if "s3://" not in line.lower():
                continue
            stripped = line.strip()
            # Allow: comments, Variable.get(), or Jinja {{ }}
            ok = (
                stripped.startswith("#")
                or "Variable.get" in line
                or "{{" in line
            )
            assert ok, f"Possibly hardcoded S3 path: {stripped}"

    def test_all_variable_get_have_default_var(self):
        """Missing default_var causes DAG parse failure in Airflow."""
        calls = re.findall(r'Variable\.get\([^)]+\)', _content())
        for call in calls:
            assert "default_var=" in call, \
                f"Variable.get() without default_var: {call}"

    def test_no_plaintext_credentials(self):
        """Common credential patterns must not appear literally."""
        content = _content().lower()
        forbidden_patterns = [
            r'aws_secret_access_key\s*=\s*["\'][^"\']+["\']',
            r'aws_access_key_id\s*=\s*["\'][A-Z0-9]{20}["\']',
        ]
        for pattern in forbidden_patterns:
            assert not re.search(pattern, content), \
                f"Possible hardcoded credential matching: {pattern}"


# ---------------------------------------------------------------------------
# Task structure
# ---------------------------------------------------------------------------

class TestTaskStructure:

    def test_all_four_tasks_defined(self):
        """All tasks from dag_spec.json must appear as GlueJobOperator() assignments."""
        content = _content()
        for task_id in ("bronze_to_silver", "quality_check_silver",
                        "silver_to_gold", "quality_check_gold"):
            # The template renders glue_job and quality_check tasks both as GlueJobOperator.
            # We match the variable assignment regardless of operator class.
            assert re.search(rf'^\s*{task_id}\s*=\s*\w+Operator\(', content, re.MULTILINE), \
                f"Task '{task_id}' not found as Operator assignment"

    def test_task_id_strings_are_correct(self):
        content = _content()
        for task_id in ("bronze_to_silver", "quality_check_silver",
                        "silver_to_gold", "quality_check_gold"):
            assert f'task_id="{task_id}"' in content, \
                f'task_id="{task_id}" not found'

    def test_all_tasks_have_execution_timeout(self):
        """Every task must have execution_timeout (the only per-task SLA bound)."""
        content = _content()
        timeout_count = content.count("execution_timeout=")
        assert timeout_count == 4, \
            f"Expected 4 execution_timeout= settings (one per task), found {timeout_count}"

    def test_dependency_chain_bronze_to_silver_to_gold(self):
        content = _content()
        assert "bronze_to_silver >> quality_check_silver" in content, \
            "bronze_to_silver >> quality_check_silver dependency missing"
        assert "quality_check_silver >> silver_to_gold" in content, \
            "quality_check_silver >> silver_to_gold dependency missing"
        assert "silver_to_gold >> quality_check_gold" in content, \
            "silver_to_gold >> quality_check_gold dependency missing"

    def test_script_paths_referenced(self):
        """Script paths from dag_spec must appear in the rendered DAG."""
        content = _content()
        for script in ("bronze_to_silver.py", "check_silver.py",
                       "silver_to_gold.py", "check_gold.py"):
            assert script in content, f"Script path '{script}' not found in DAG"

    def test_adop_run_id_passed_to_all_tasks(self):
        """ADOP_RUN_ID must be injected into every task's script_args."""
        count = _content().count("--ADOP_RUN_ID")
        assert count >= 4, \
            f"Expected ≥ 4 --ADOP_RUN_ID occurrences (one per task), found {count}"


# ---------------------------------------------------------------------------
# Glue-specific arguments
# ---------------------------------------------------------------------------

class TestGlueArguments:

    def test_customer_orders_quarantine_uri_in_bronze_to_silver(self):
        """Quarantine URI variable must be forwarded to the bronze→silver job."""
        assert "CUSTOMER_ORDERS_QUARANTINE_URI" in _content(), \
            "CUSTOMER_ORDERS_QUARANTINE_URI not found in DAG"

    def test_token_secret_in_bronze_to_silver(self):
        """Tokenisation secret must be forwarded (PII masking of credit_card_number)."""
        assert "CUSTOMER_ORDERS_TOKEN_SECRET_ID" in _content(), \
            "CUSTOMER_ORDERS_TOKEN_SECRET_ID not found in DAG"

    def test_glue_script_s3_path_variable(self):
        assert 'Variable.get("glue_script_s3_path"' in _content(), \
            "glue_script_s3_path Variable.get not found"

    def test_glue_iam_role_variable(self):
        assert 'Variable.get("glue_iam_role"' in _content(), \
            "glue_iam_role Variable.get not found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
