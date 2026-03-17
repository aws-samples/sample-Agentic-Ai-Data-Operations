"""
Integration tests for the sales_transactions Airflow DAG.

These tests verify:
- Task dependencies are valid (upstream/downstream)
- TaskGroups exist and contain expected tasks
- Pipeline runs end-to-end when tasks are executed in order (dry run)
- schedule.yaml cron matches DAG schedule

We mock Airflow imports so these tests work without a running Airflow instance.
"""

import importlib
import os
import sys
import types
import unittest
from collections import OrderedDict
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
# Mock infrastructure (same approach as unit tests, but with richer tracking)
# ---------------------------------------------------------------------------

class MockVariable:
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
    """TaskGroup mock that tracks membership and group-level dependencies."""

    _groups = OrderedDict()

    def __init__(self, group_id, **kwargs):
        self.group_id = group_id
        self.tasks = []
        self._downstream_groups = []
        self._upstream_groups = []
        MockTaskGroup._groups[group_id] = self

    def __enter__(self):
        MockTaskGroup._current_group = self
        return self

    def __exit__(self, *args):
        MockTaskGroup._current_group = None

    def __rshift__(self, other):
        if isinstance(other, MockTaskGroup):
            self._downstream_groups.append(other)
            other._upstream_groups.append(self)
        return other

    def __rrshift__(self, other):
        if isinstance(other, MockTaskGroup):
            other._downstream_groups.append(self)
            self._upstream_groups.append(other)
        return self


MockTaskGroup._current_group = None


class MockOperator:
    """PythonOperator mock that records task parameters and dependencies."""

    _all_tasks = []

    def __init__(self, task_id=None, python_callable=None, trigger_rule=None,
                 sla=None, **kwargs):
        self.task_id = task_id
        self.python_callable = python_callable
        self.trigger_rule = trigger_rule or "all_success"
        self.sla = sla
        self.upstream_list = []
        self.downstream_list = []
        self._kwargs = kwargs
        MockOperator._all_tasks.append(self)

        # Register with current task group
        current = getattr(MockTaskGroup, "_current_group", None)
        if current is not None:
            current.tasks.append(self)

    def __rshift__(self, other):
        self.downstream_list.append(other)
        if hasattr(other, "upstream_list"):
            other.upstream_list.append(self)
        return other

    def __rrshift__(self, other):
        return self


class MockDAG:
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
    MockOperator._all_tasks = []
    MockTaskGroup._groups = OrderedDict()
    MockTaskGroup._current_group = None
    MockDAG._instance = None


def _build_airflow_mocks():
    mods = {}
    airflow_mod = types.ModuleType("airflow")
    airflow_mod.DAG = MockDAG
    mods["airflow"] = airflow_mod

    models_mod = types.ModuleType("airflow.models")
    models_mod.Variable = MockVariable
    mods["airflow.models"] = models_mod

    operators_mod = types.ModuleType("airflow.operators")
    mods["airflow.operators"] = operators_mod

    python_mod = types.ModuleType("airflow.operators.python")
    python_mod.PythonOperator = MockOperator
    mods["airflow.operators.python"] = python_mod

    bash_mod = types.ModuleType("airflow.operators.bash")
    bash_mod.BashOperator = MockOperator
    mods["airflow.operators.bash"] = bash_mod

    utils_mod = types.ModuleType("airflow.utils")
    mods["airflow.utils"] = utils_mod

    tg_mod = types.ModuleType("airflow.utils.task_group")
    tg_mod.TaskGroup = MockTaskGroup
    mods["airflow.utils.task_group"] = tg_mod

    return mods


def _load_dag_module():
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
# Integration Tests
# ---------------------------------------------------------------------------

class TestTaskDependencies(unittest.TestCase):
    """Verify that all task dependencies are valid (upstream/downstream)."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_dag_module()
        cls.tasks = MockOperator._all_tasks
        cls.task_map = {t.task_id: t for t in cls.tasks}
        cls.groups = MockTaskGroup._groups

    def test_sensor_s3_source_downstream_is_ingest(self):
        """sensor_s3_source must flow into ingest_to_bronze."""
        sensor = self.task_map["sensor_s3_source"]
        downstream_ids = [t.task_id for t in sensor.downstream_list if hasattr(t, "task_id")]
        self.assertIn("ingest_to_bronze", downstream_ids)

    def test_bronze_to_silver_downstream_is_quality_silver(self):
        """bronze_to_silver must flow into quality_check_silver."""
        task = self.task_map["bronze_to_silver"]
        downstream_ids = [t.task_id for t in task.downstream_list if hasattr(t, "task_id")]
        self.assertIn("quality_check_silver", downstream_ids)

    def test_silver_to_gold_downstream_is_quality_gold(self):
        """silver_to_gold must flow into quality_check_gold."""
        task = self.task_map["silver_to_gold"]
        downstream_ids = [t.task_id for t in task.downstream_list if hasattr(t, "task_id")]
        self.assertIn("quality_check_gold", downstream_ids)

    def test_update_catalog_downstream_is_semantic_metadata(self):
        """update_catalog must flow into update_semantic_metadata."""
        task = self.task_map["update_catalog"]
        downstream_ids = [t.task_id for t in task.downstream_list if hasattr(t, "task_id")]
        self.assertIn("update_semantic_metadata", downstream_ids)

    def test_all_downstream_references_are_valid_tasks(self):
        """Every downstream reference must point to a task that exists."""
        valid_ids = set(self.task_map.keys())
        for task in self.tasks:
            for downstream in task.downstream_list:
                if hasattr(downstream, "task_id"):
                    self.assertIn(
                        downstream.task_id, valid_ids,
                        f"Task '{task.task_id}' references nonexistent downstream '{downstream.task_id}'"
                    )


class TestTaskGroups(unittest.TestCase):
    """Verify that TaskGroups exist and contain expected tasks."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_dag_module()
        cls.groups = MockTaskGroup._groups

    def test_extract_group_exists(self):
        """TaskGroup 'extract' must exist."""
        self.assertIn("extract", self.groups)

    def test_transform_group_exists(self):
        """TaskGroup 'transform' must exist."""
        self.assertIn("transform", self.groups)

    def test_curate_group_exists(self):
        """TaskGroup 'curate' must exist."""
        self.assertIn("curate", self.groups)

    def test_catalog_group_exists(self):
        """TaskGroup 'catalog' must exist."""
        self.assertIn("catalog", self.groups)

    def test_extract_group_tasks(self):
        """extract group must contain sensor_s3_source and ingest_to_bronze."""
        group = self.groups["extract"]
        task_ids = {t.task_id for t in group.tasks}
        expected = {"sensor_s3_source", "ingest_to_bronze"}
        self.assertEqual(task_ids, expected, f"extract tasks: expected {expected}, got {task_ids}")

    def test_transform_group_tasks(self):
        """transform group must contain bronze_to_silver and quality_check_silver."""
        group = self.groups["transform"]
        task_ids = {t.task_id for t in group.tasks}
        expected = {"bronze_to_silver", "quality_check_silver"}
        self.assertEqual(task_ids, expected, f"transform tasks: expected {expected}, got {task_ids}")

    def test_curate_group_tasks(self):
        """curate group must contain silver_to_gold and quality_check_gold."""
        group = self.groups["curate"]
        task_ids = {t.task_id for t in group.tasks}
        expected = {"silver_to_gold", "quality_check_gold"}
        self.assertEqual(task_ids, expected, f"curate tasks: expected {expected}, got {task_ids}")

    def test_catalog_group_tasks(self):
        """catalog group must contain update_catalog and update_semantic_metadata."""
        group = self.groups["catalog"]
        task_ids = {t.task_id for t in group.tasks}
        expected = {"update_catalog", "update_semantic_metadata"}
        self.assertEqual(task_ids, expected, f"catalog tasks: expected {expected}, got {task_ids}")

    def test_group_order(self):
        """TaskGroups must be in order: extract -> transform -> curate -> catalog."""
        group_ids = list(self.groups.keys())
        self.assertEqual(
            group_ids,
            ["extract", "transform", "curate", "catalog"],
            f"TaskGroup order: {group_ids}",
        )

    def test_group_sequential_dependencies(self):
        """Each TaskGroup must depend on the previous one."""
        extract = self.groups["extract"]
        transform = self.groups["transform"]
        curate = self.groups["curate"]
        catalog = self.groups["catalog"]

        # extract -> transform
        self.assertIn(transform, extract._downstream_groups,
                       "extract must have transform as downstream")
        # transform -> curate
        self.assertIn(curate, transform._downstream_groups,
                       "transform must have curate as downstream")
        # curate -> catalog
        self.assertIn(catalog, curate._downstream_groups,
                       "curate must have catalog as downstream")


class TestPipelineDryRun(unittest.TestCase):
    """Dry-run: verify all task callables exist and are callable."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_dag_module()
        cls.tasks = MockOperator._all_tasks
        cls.task_map = {t.task_id: t for t in cls.tasks}

    def test_all_callables_are_functions(self):
        """Every task's python_callable must be a callable function."""
        for task in self.tasks:
            self.assertTrue(
                callable(task.python_callable),
                f"Task '{task.task_id}' python_callable is not callable",
            )

    def test_execution_order_is_valid(self):
        """Tasks must be executable in the correct topological order.

        This verifies that each task's upstream dependencies appear
        earlier in the expected execution order.
        """
        expected_order = [
            "sensor_s3_source",
            "ingest_to_bronze",
            "bronze_to_silver",
            "quality_check_silver",
            "silver_to_gold",
            "quality_check_gold",
            "update_catalog",
            "update_semantic_metadata",
        ]
        position = {task_id: i for i, task_id in enumerate(expected_order)}

        for task in self.tasks:
            task_pos = position.get(task.task_id)
            self.assertIsNotNone(task_pos, f"Task '{task.task_id}' not in expected order")
            for upstream in task.upstream_list:
                if hasattr(upstream, "task_id"):
                    upstream_pos = position.get(upstream.task_id)
                    self.assertIsNotNone(
                        upstream_pos,
                        f"Upstream '{upstream.task_id}' of '{task.task_id}' not in expected order",
                    )
                    self.assertLess(
                        upstream_pos, task_pos,
                        f"Upstream '{upstream.task_id}' (pos={upstream_pos}) must come before "
                        f"'{task.task_id}' (pos={task_pos})",
                    )

    def test_quality_gate_tasks_have_trigger_rule_all_success(self):
        """Quality gate tasks must use trigger_rule='all_success'."""
        quality_tasks = ["quality_check_silver", "quality_check_gold"]
        for task_id in quality_tasks:
            task = self.task_map[task_id]
            self.assertEqual(
                task.trigger_rule, "all_success",
                f"Quality task '{task_id}' trigger_rule={task.trigger_rule}, expected 'all_success'",
            )


class TestScheduleMatchesDAG(unittest.TestCase):
    """Verify schedule.yaml cron matches DAG schedule."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_dag_module()
        cls.dag = MockDAG._instance
        with open(SCHEDULE_YAML, "r") as f:
            cls.schedule = yaml.safe_load(f)

    def test_cron_matches(self):
        """schedule.yaml cron must match DAG schedule."""
        yaml_cron = self.schedule.get("schedule", {}).get("cron")
        dag_schedule = self.dag.schedule
        self.assertEqual(
            yaml_cron, dag_schedule,
            f"schedule.yaml cron='{yaml_cron}' does not match DAG schedule='{dag_schedule}'",
        )

    def test_retries_match(self):
        """schedule.yaml max_retries must match DAG default_args retries."""
        yaml_retries = self.schedule.get("schedule", {}).get("max_retries")
        dag_retries = self.dag.default_args.get("retries")
        self.assertEqual(
            yaml_retries, dag_retries,
            f"schedule.yaml max_retries={yaml_retries} != DAG retries={dag_retries}",
        )

    def test_retry_delay_matches(self):
        """schedule.yaml retry_delay_seconds must match DAG retry_delay."""
        from datetime import timedelta
        yaml_delay = self.schedule.get("schedule", {}).get("retry_delay_seconds")
        dag_delay = self.dag.default_args.get("retry_delay")
        if isinstance(dag_delay, timedelta):
            dag_delay_seconds = int(dag_delay.total_seconds())
        else:
            dag_delay_seconds = dag_delay
        self.assertEqual(
            yaml_delay, dag_delay_seconds,
            f"schedule.yaml retry_delay={yaml_delay}s != DAG retry_delay={dag_delay_seconds}s",
        )

    def test_workload_name_matches(self):
        """schedule.yaml workload name must match DAG workload."""
        yaml_workload = self.schedule.get("schedule", {}).get("workload")
        self.assertEqual(yaml_workload, "sales_transactions")


if __name__ == "__main__":
    unittest.main()
