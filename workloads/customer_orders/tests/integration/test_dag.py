"""Integration tests for customer_orders DAG — file-system and spec coherence.

These tests verify that:
  - The rendered DAG file is present at the canonical location
  - All TRANSFORM scripts referenced by the DAG exist on disk
    (quality scripts are Phase 4.4 output — not required to exist at Phase 4.5)
  - Config files (dag_spec.json, quality_rules.yaml, source.yaml, …) exist and are valid
  - dag_spec.json values are consistent with human_answers in run/context.json
  - Logs directory is present (required by the logging hook)
  - Codegen header is present and well-formed

No Airflow runtime is required; no AWS calls are made.
"""

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
TEST_FILE = Path(__file__).resolve()
# test_dag.py → integration → tests → customer_orders → workloads → project_root
WORKLOAD_DIR = TEST_FILE.parent.parent.parent          # workloads/customer_orders
PROJECT_ROOT = WORKLOAD_DIR.parent.parent              # repo root
DAG_FILE = WORKLOAD_DIR / "dags" / "customer_orders_pipeline.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_dag_spec() -> dict:
    path = WORKLOAD_DIR / "config" / "dag_spec.json"
    with path.open() as fh:
        return json.load(fh)


def _load_run_context() -> dict:
    path = WORKLOAD_DIR / "run" / "context.json"
    with path.open() as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# DAG file existence
# ---------------------------------------------------------------------------

class TestDagFileExists:

    def test_dag_file_at_canonical_location(self):
        assert DAG_FILE.exists(), \
            f"DAG file not found at canonical location: {DAG_FILE}"

    def test_dag_file_is_not_empty(self):
        assert DAG_FILE.stat().st_size > 0, "DAG file is empty"

    def test_dag_file_has_codegen_header(self):
        """Confirms render_artifact was used (not fs_write directly)."""
        import re
        content = DAG_FILE.read_text(encoding="utf-8")
        lines = content.split("\n")
        assert lines[0].startswith("# spec_hash:"), \
            "First line must be '# spec_hash:…' — DAG was not written by renderer"
        assert lines[1].startswith("# template_id:"), \
            "Second line must be '# template_id:…'"
        assert re.search(r"# template_id:\s*airflow_dag", lines[1]), \
            f"template_id must be airflow_dag, got: {lines[1]}"


# ---------------------------------------------------------------------------
# Referenced TRANSFORM scripts exist on disk
# (Quality scripts are Phase 4.4 output; their presence is not gated here)
# ---------------------------------------------------------------------------

class TestReferencedTransformScriptsExist:
    """Checks that Phase 4.3 transform script_paths point to real files."""

    def test_bronze_to_silver_script_exists(self):
        p = PROJECT_ROOT / "workloads/customer_orders/scripts/transform/bronze_to_silver.py"
        assert p.exists(), f"bronze_to_silver script not found: {p}"

    def test_silver_to_gold_script_exists(self):
        p = PROJECT_ROOT / "workloads/customer_orders/scripts/transform/silver_to_gold.py"
        assert p.exists(), f"silver_to_gold script not found: {p}"

    def test_all_dag_spec_script_paths_reference_valid_extensions(self):
        """Every script_path in dag_spec ends in .py (no stale .sql or missing ext)."""
        spec = _load_dag_spec()
        for task in spec.get("tasks", []):
            sp = task.get("script_path", "")
            if sp:
                assert sp.endswith(".py"), \
                    f"task {task['task_id']} script_path does not end in .py: {sp!r}"


# ---------------------------------------------------------------------------
# Config files exist and are valid
# ---------------------------------------------------------------------------

class TestConfigFiles:

    def test_dag_spec_exists(self):
        assert (WORKLOAD_DIR / "config" / "dag_spec.json").exists()

    def test_source_yaml_exists(self):
        assert (WORKLOAD_DIR / "config" / "source.yaml").exists()

    def test_transformations_yaml_exists(self):
        assert (WORKLOAD_DIR / "config" / "transformations.yaml").exists()

    def test_quality_rules_yaml_exists(self):
        assert (WORKLOAD_DIR / "config" / "quality_rules.yaml").exists()

    def test_run_context_exists(self):
        assert (WORKLOAD_DIR / "run" / "context.json").exists()

    def test_dag_spec_is_valid_json(self):
        spec = _load_dag_spec()   # raises if invalid
        assert "dataset_name" in spec
        assert spec["dataset_name"] == "customer_orders"
        assert "schedule" in spec
        assert "tasks" in spec

    def test_run_context_is_valid_json(self):
        ctx = _load_run_context()
        assert ctx["schema_version"] == "v1"
        assert ctx["workload_name"] == "customer_orders"


# ---------------------------------------------------------------------------
# dag_spec ↔ run/context.json coherence
# ---------------------------------------------------------------------------

class TestSpecContextCoherence:
    """Ensures the DAG spec reflects the human answers without drift."""

    def test_schedule_matches_human_answer(self):
        spec = _load_dag_spec()
        ctx = _load_run_context()
        human_schedule = ctx["human_answers"]["schedule"]
        assert spec["schedule"]["cron"] == human_schedule, (
            f"dag_spec.schedule.cron ({spec['schedule']['cron']!r}) "
            f"does not match human_answers.schedule ({human_schedule!r})"
        )

    def test_timezone_matches_human_answer(self):
        spec = _load_dag_spec()
        ctx = _load_run_context()
        human_tz = ctx["human_answers"]["schedule_timezone"]
        assert spec["schedule"]["timezone"] == human_tz, (
            f"dag_spec.schedule.timezone ({spec['schedule']['timezone']!r}) "
            f"does not match human_answers.schedule_timezone ({human_tz!r})"
        )

    def test_catchup_is_false_in_spec(self):
        assert _load_dag_spec()["schedule"]["catchup"] is False

    def test_max_active_runs_is_one_in_spec(self):
        assert _load_dag_spec()["schedule"]["max_active_runs"] == 1

    def test_retries_count_is_three(self):
        assert _load_dag_spec()["retries"]["count"] == 3

    def test_retries_backoff_is_true(self):
        assert _load_dag_spec()["retries"]["backoff"] is True

    def test_sla_deadline_is_180_minutes(self):
        assert _load_dag_spec()["sla"]["deadline_minutes"] == 180

    def test_failure_handling_is_sns_alert(self):
        fh = _load_dag_spec()["failure_handling"]
        assert fh["on_failure_callback"] == "sns_alert"

    def test_dataset_name_consistent(self):
        spec = _load_dag_spec()
        ctx = _load_run_context()
        assert spec["dataset_name"] == ctx["workload_name"] == "customer_orders"


# ---------------------------------------------------------------------------
# dag_spec task definitions
# ---------------------------------------------------------------------------

class TestDagSpecTasks:

    def test_four_tasks_defined(self):
        tasks = _load_dag_spec()["tasks"]
        task_ids = [t["task_id"] for t in tasks]
        assert len(task_ids) == 4, f"Expected 4 tasks, got {len(task_ids)}: {task_ids}"

    def test_required_task_ids_present(self):
        spec = _load_dag_spec()
        task_ids = {t["task_id"] for t in spec["tasks"]}
        for expected in ("bronze_to_silver", "quality_check_silver",
                         "silver_to_gold", "quality_check_gold"):
            assert expected in task_ids, f"Task '{expected}' missing from spec"

    def test_dependency_chain_in_spec(self):
        spec = _load_dag_spec()
        tasks = {t["task_id"]: t for t in spec["tasks"]}
        assert tasks["bronze_to_silver"]["depends_on"] == []
        assert "bronze_to_silver" in tasks["quality_check_silver"]["depends_on"]
        assert "quality_check_silver" in tasks["silver_to_gold"]["depends_on"]
        assert "silver_to_gold" in tasks["quality_check_gold"]["depends_on"]

    def test_quality_gates_threshold_silver(self):
        spec = _load_dag_spec()
        tasks = {t["task_id"]: t for t in spec["tasks"]}
        assert tasks["quality_check_silver"]["params"]["threshold"] == 0.8

    def test_quality_gates_threshold_gold(self):
        spec = _load_dag_spec()
        tasks = {t["task_id"]: t for t in spec["tasks"]}
        assert tasks["quality_check_gold"]["params"]["threshold"] == 0.95

    def test_critical_tasks_in_sla(self):
        sla = _load_dag_spec()["sla"]
        assert "quality_check_silver" in sla["critical_tasks"]
        assert "quality_check_gold" in sla["critical_tasks"]

    def test_gdpr_tag_present(self):
        tags = _load_dag_spec().get("tags", [])
        assert "gdpr" in tags, f"'gdpr' tag missing from dag_spec: {tags}"


# ---------------------------------------------------------------------------
# Logs directory
# ---------------------------------------------------------------------------

class TestLogsDirectory:

    def test_logs_dir_exists(self):
        logs_dir = WORKLOAD_DIR / "logs"
        assert logs_dir.exists() and logs_dir.is_dir(), \
            f"logs/ directory missing at {logs_dir}"

    def test_logs_readme_exists(self):
        readme = WORKLOAD_DIR / "logs" / "README.md"
        assert readme.exists(), f"logs/README.md not found at {readme}"


# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------

class TestDirectoryStructure:

    def test_unit_tests_dir_exists(self):
        assert (WORKLOAD_DIR / "tests" / "unit").is_dir()

    def test_integration_tests_dir_exists(self):
        assert (WORKLOAD_DIR / "tests" / "integration").is_dir()

    def test_dags_dir_exists(self):
        assert (WORKLOAD_DIR / "dags").is_dir()

    def test_scripts_transform_dir_exists(self):
        assert (WORKLOAD_DIR / "scripts" / "transform").is_dir()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
