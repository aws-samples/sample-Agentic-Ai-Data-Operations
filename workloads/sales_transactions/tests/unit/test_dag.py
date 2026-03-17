"""
Unit tests for the sales_transactions Airflow DAG.

These tests verify DAG structure, configuration, and compliance with
the rules defined in SKILLS.md without requiring a running Airflow instance.
We mock Airflow imports so the tests work in any Python environment.
"""

import ast
import importlib
import os
import sys
import types
import unittest
from unittest import mock

import yaml

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
WORKLOAD_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(os.path.dirname(WORKLOAD_DIR))
DAG_FILE = os.path.join(WORKLOAD_DIR, "dags", "sales_transactions_dag.py")
SCHEDULE_YAML = os.path.join(WORKLOAD_DIR, "config", "schedule.yaml")


# ---------------------------------------------------------------------------
# Helpers: build a lightweight Airflow mock layer
# ---------------------------------------------------------------------------

class MockVariable:
    """Mock for airflow.models.Variable."""

    @staticmethod
    def get(key, default_var=None):
        defaults = {
            "s3_raw_bucket": "data-lake-raw",
            "s3_raw_prefix_sales": "sales/transactions/",
            "s3_bronze_bucket": "data-lake-bronze",
            "s3_bronze_prefix_sales": "sales/transactions/",
            "quality_threshold_silver_sales": "0.80",
            "quality_threshold_gold_sales": "0.95",
            "sns_alert_topic_arn": "arn:aws:sns:us-east-1:ACCOUNT_ID:data-pipeline-alerts",
            "base_path": PROJECT_ROOT,
        }
        return defaults.get(key, default_var)


class MockTaskGroup:
    """Minimal TaskGroup mock that captures tasks."""

    _groups = {}

    def __init__(self, group_id, **kwargs):
        self.group_id = group_id
        self.tasks = []
        MockTaskGroup._groups[group_id] = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def __rshift__(self, other):
        return other

    def __rrshift__(self, other):
        return self


class MockOperator:
    """Minimal PythonOperator mock that records parameters."""

    _all_tasks = []

    def __init__(self, task_id=None, python_callable=None, trigger_rule=None,
                 sla=None, **kwargs):
        self.task_id = task_id
        self.python_callable = python_callable
        self.trigger_rule = trigger_rule or "all_success"
        self.sla = sla
        self.upstream_list = []
        self.downstream_list = []
        # Capture kwargs that may include default_args overrides
        self._kwargs = kwargs
        MockOperator._all_tasks.append(self)

    def __rshift__(self, other):
        self.downstream_list.append(other)
        other.upstream_list.append(self)
        return other

    def __rrshift__(self, other):
        return self


class MockDAG:
    """Minimal DAG mock that stores configuration."""

    _instance = None

    def __init__(self, dag_id=None, default_args=None, description=None,
                 schedule=None, start_date=None, catchup=None,
                 max_active_runs=None, tags=None, doc_md=None, **kwargs):
        self.dag_id = dag_id
        self.default_args = default_args or {}
        self.description = description
        self.schedule = schedule
        self.start_date = start_date
        self.catchup = catchup
        self.max_active_runs = max_active_runs
        self.tags = tags or []
        self.doc_md = doc_md
        MockDAG._instance = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _reset_mocks():
    """Reset all class-level state."""
    MockOperator._all_tasks = []
    MockTaskGroup._groups = {}
    MockDAG._instance = None


def _build_airflow_mocks():
    """Build a hierarchy of mock modules that replaces Airflow."""
    mods = {}

    # airflow
    airflow_mod = types.ModuleType("airflow")
    airflow_mod.DAG = MockDAG
    mods["airflow"] = airflow_mod

    # airflow.models
    models_mod = types.ModuleType("airflow.models")
    models_mod.Variable = MockVariable
    mods["airflow.models"] = models_mod

    # airflow.operators
    operators_mod = types.ModuleType("airflow.operators")
    mods["airflow.operators"] = operators_mod

    # airflow.operators.python
    python_mod = types.ModuleType("airflow.operators.python")
    python_mod.PythonOperator = MockOperator
    mods["airflow.operators.python"] = python_mod

    # airflow.operators.bash
    bash_mod = types.ModuleType("airflow.operators.bash")
    bash_mod.BashOperator = MockOperator
    mods["airflow.operators.bash"] = bash_mod

    # airflow.utils
    utils_mod = types.ModuleType("airflow.utils")
    mods["airflow.utils"] = utils_mod

    # airflow.utils.task_group
    tg_mod = types.ModuleType("airflow.utils.task_group")
    tg_mod.TaskGroup = MockTaskGroup
    mods["airflow.utils.task_group"] = tg_mod

    return mods


def _load_dag_module():
    """Import the DAG module using our mocked Airflow layer."""
    _reset_mocks()
    mock_modules = _build_airflow_mocks()

    with mock.patch.dict(sys.modules, mock_modules):
        spec = importlib.util.spec_from_file_location(
            "sales_transactions_dag", DAG_FILE
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDAGFileImport(unittest.TestCase):
    """Verify that the DAG file is importable and syntactically correct."""

    def test_dag_file_exists(self):
        """DAG Python file must exist on disk."""
        self.assertTrue(os.path.isfile(DAG_FILE), f"DAG file not found: {DAG_FILE}")

    def test_dag_file_valid_python_syntax(self):
        """DAG file must parse as valid Python (AST check)."""
        with open(DAG_FILE, "r") as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            self.fail(f"DAG file has a syntax error: {e}")

    def test_dag_module_importable(self):
        """DAG module must import without errors (with mocked Airflow)."""
        mod = _load_dag_module()
        self.assertIsNotNone(mod)


class TestDAGConfiguration(unittest.TestCase):
    """Verify DAG-level settings match SKILLS.md requirements."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_dag_module()
        cls.dag = MockDAG._instance

    def test_dag_id(self):
        """dag_id must follow the naming convention."""
        self.assertIsNotNone(self.dag, "No DAG instance was created")
        self.assertEqual(self.dag.dag_id, "sales_transactions_daily")

    def test_catchup_false(self):
        """catchup must be False."""
        self.assertFalse(self.dag.catchup)

    def test_max_active_runs_one(self):
        """max_active_runs must be 1."""
        self.assertEqual(self.dag.max_active_runs, 1)

    def test_doc_md_present(self):
        """doc_md must be set on the DAG."""
        self.assertIsNotNone(self.dag.doc_md)
        self.assertTrue(len(self.dag.doc_md) > 0, "doc_md is empty")

    def test_tags_present(self):
        """DAG must have the required tags."""
        required_tags = {"sales", "data-onboarding", "daily"}
        self.assertTrue(
            required_tags.issubset(set(self.dag.tags)),
            f"Missing tags. Required: {required_tags}, got: {self.dag.tags}",
        )

    def test_schedule_is_cron(self):
        """DAG schedule must be the expected cron expression."""
        self.assertEqual(self.dag.schedule, "0 6 * * *")

    def test_start_date_is_fixed(self):
        """start_date must be a fixed past date, not datetime.now()."""
        from datetime import datetime as dt
        self.assertIsNotNone(self.dag.start_date)
        self.assertIsInstance(self.dag.start_date, dt)
        # Must be in the past (before 2026)
        self.assertLess(self.dag.start_date.year, 2026)

    def test_default_args_retries(self):
        """default_args must have retries=3."""
        self.assertEqual(self.dag.default_args.get("retries"), 3)

    def test_default_args_exponential_backoff(self):
        """default_args must have retry_exponential_backoff=True."""
        self.assertTrue(self.dag.default_args.get("retry_exponential_backoff"))

    def test_default_args_on_failure_callback(self):
        """default_args must have on_failure_callback set."""
        callback = self.dag.default_args.get("on_failure_callback")
        self.assertIsNotNone(callback, "on_failure_callback not set in default_args")
        self.assertTrue(callable(callback), "on_failure_callback is not callable")


class TestDAGTasks(unittest.TestCase):
    """Verify correct number of tasks and their properties."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_dag_module()
        cls.tasks = MockOperator._all_tasks
        cls.dag = MockDAG._instance

    def test_task_count(self):
        """DAG must have exactly 8 tasks."""
        self.assertEqual(len(self.tasks), 8, f"Expected 8 tasks, got {len(self.tasks)}")

    def test_expected_task_ids(self):
        """All expected task IDs must be present."""
        expected = {
            "sensor_s3_source",
            "ingest_to_bronze",
            "bronze_to_silver",
            "quality_check_silver",
            "silver_to_gold",
            "quality_check_gold",
            "update_catalog",
            "update_semantic_metadata",
        }
        actual = {t.task_id for t in self.tasks}
        self.assertEqual(expected, actual, f"Task ID mismatch. Missing: {expected - actual}, extra: {actual - expected}")

    def test_all_tasks_have_on_failure_callback(self):
        """Every task must have on_failure_callback (via default_args)."""
        callback = self.dag.default_args.get("on_failure_callback")
        self.assertIsNotNone(
            callback,
            "on_failure_callback not set in default_args (applies to all tasks)",
        )

    def test_all_tasks_have_retries(self):
        """Every task must have retries=3 (via default_args)."""
        retries = self.dag.default_args.get("retries")
        self.assertEqual(retries, 3, f"default_args retries={retries}, expected 3")

    def test_all_tasks_have_callable(self):
        """Every PythonOperator task must have a python_callable."""
        for task in self.tasks:
            self.assertIsNotNone(
                task.python_callable,
                f"Task '{task.task_id}' has no python_callable",
            )


class TestDAGNoCycles(unittest.TestCase):
    """Verify there are no cycles in task dependencies."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_dag_module()
        cls.tasks = MockOperator._all_tasks

    def test_no_cycles(self):
        """Task dependency graph must be a DAG (no cycles)."""
        # Build adjacency list
        task_map = {t.task_id: t for t in self.tasks}
        visited = set()
        in_stack = set()

        def has_cycle(task_id):
            if task_id in in_stack:
                return True
            if task_id in visited:
                return False
            visited.add(task_id)
            in_stack.add(task_id)
            task = task_map.get(task_id)
            if task:
                for downstream in task.downstream_list:
                    if hasattr(downstream, "task_id"):
                        if has_cycle(downstream.task_id):
                            return True
            in_stack.discard(task_id)
            return False

        for task_id in task_map:
            self.assertFalse(has_cycle(task_id), f"Cycle detected involving task: {task_id}")


class TestDAGNoHardcodedSecrets(unittest.TestCase):
    """Verify no hardcoded secrets, bucket names, or account IDs in DAG."""

    def test_no_hardcoded_account_ids(self):
        """DAG file must not contain real AWS account IDs."""
        with open(DAG_FILE, "r") as f:
            source = f.read()
        # The placeholder ACCOUNT_ID is acceptable; real 12-digit IDs are not
        import re
        # Look for 12-digit numbers that could be AWS account IDs (not in comments)
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip the default_var strings (these are placeholders)
            if "default_var" in line or "ACCOUNT_ID" in line:
                continue
            matches = re.findall(r'\b\d{12}\b', line)
            self.assertEqual(
                len(matches), 0,
                f"Possible hardcoded AWS account ID on line {i}: {line.strip()}"
            )

    def test_no_provide_context(self):
        """DAG must not use deprecated provide_context=True."""
        with open(DAG_FILE, "r") as f:
            source = f.read()
        self.assertNotIn("provide_context", source)

    def test_no_subdagoperator(self):
        """DAG must not use deprecated SubDagOperator."""
        with open(DAG_FILE, "r") as f:
            source = f.read()
        self.assertNotIn("SubDagOperator", source)

    def test_no_datetime_now_start_date(self):
        """start_date must not be datetime.now()."""
        with open(DAG_FILE, "r") as f:
            source = f.read()
        self.assertNotIn("datetime.now()", source)


class TestScheduleYAML(unittest.TestCase):
    """Verify schedule.yaml is valid and complete."""

    def test_schedule_yaml_exists(self):
        """schedule.yaml must exist."""
        self.assertTrue(os.path.isfile(SCHEDULE_YAML), f"File not found: {SCHEDULE_YAML}")

    def test_schedule_yaml_valid(self):
        """schedule.yaml must be valid YAML."""
        with open(SCHEDULE_YAML, "r") as f:
            data = yaml.safe_load(f)
        self.assertIsInstance(data, dict)

    def test_schedule_has_cron(self):
        """schedule.yaml must have a cron expression."""
        with open(SCHEDULE_YAML, "r") as f:
            data = yaml.safe_load(f)
        cron = data.get("schedule", {}).get("cron")
        self.assertIsNotNone(cron, "cron not found in schedule.yaml")
        self.assertEqual(cron, "0 6 * * *")

    def test_schedule_has_retries(self):
        """schedule.yaml must define retry policy."""
        with open(SCHEDULE_YAML, "r") as f:
            data = yaml.safe_load(f)
        sched = data.get("schedule", {})
        self.assertEqual(sched.get("max_retries"), 3)
        self.assertEqual(sched.get("retry_delay_seconds"), 300)
        self.assertEqual(sched.get("retry_backoff"), "exponential")

    def test_schedule_has_sla(self):
        """schedule.yaml must define SLA."""
        with open(SCHEDULE_YAML, "r") as f:
            data = yaml.safe_load(f)
        sla = data.get("schedule", {}).get("sla_minutes")
        self.assertIsNotNone(sla)
        self.assertEqual(sla, 60)

    def test_schedule_has_failure_notification(self):
        """schedule.yaml must define failure notification."""
        with open(SCHEDULE_YAML, "r") as f:
            data = yaml.safe_load(f)
        notif = data.get("schedule", {}).get("failure_notification")
        self.assertIsNotNone(notif)
        self.assertIn("topic_arn", notif)


if __name__ == "__main__":
    unittest.main()
