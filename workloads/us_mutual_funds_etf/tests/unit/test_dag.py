"""
Unit tests for us_mutual_funds_etf_dag.py

Tests DAG structure, configuration, task count, dependencies, and Airflow best practices
without requiring a running Airflow instance. Uses mocking to work in any Python environment.
"""

import ast
import os
import sys
import types
from datetime import datetime, timedelta
from unittest import mock

import pytest
import yaml


# ============================================================================
# Path Constants
# ============================================================================

WORKLOAD_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(os.path.dirname(WORKLOAD_DIR))
DAG_FILE = os.path.join(WORKLOAD_DIR, "dags", "us_mutual_funds_etf_dag.py")
SCHEDULE_YAML = os.path.join(WORKLOAD_DIR, "config", "schedule.yaml")


# ============================================================================
# Mock Airflow Classes
# ============================================================================

class MockVariable:
    """Mock for airflow.models.Variable"""

    @staticmethod
    def get(key, default_var=None):
        defaults = {
            "finsights_s3_bucket": "your-datalake-bucket",
            "finsights_glue_role": "GlueServiceRole",
            "aws_region": "us-east-1",
            "glue_version": "4.0",
            "glue_worker_type": "G.1X",
            "slack_connection_id": "slack_data_alerts",
        }
        return defaults.get(key, default_var)


class MockTaskGroup:
    """Mock for airflow.utils.task_group.TaskGroup"""

    _groups = {}
    _current_group = None

    def __init__(self, group_id, **kwargs):
        self.group_id = group_id
        self.tasks = []
        self.upstream_list = []
        self.downstream_list = []
        MockTaskGroup._groups[group_id] = self

    def __enter__(self):
        MockTaskGroup._current_group = self
        return self

    def __exit__(self, *args):
        MockTaskGroup._current_group = None

    def __rshift__(self, other):
        # When TaskGroup >> TaskGroup or TaskGroup >> Task
        # Connect all tasks in self to all tasks in other (if other is a group)
        # Or connect all tasks in self to other (if other is a task)
        if isinstance(other, MockTaskGroup):
            # Connect all tasks in self to all tasks in other
            for task in self.tasks:
                for other_task in other.tasks:
                    task.downstream_list.append(other_task)
                    other_task.upstream_list.append(task)
            self.downstream_list.append(other)
            other.upstream_list.append(self)
        elif isinstance(other, MockOperator):
            # Connect all tasks in self to other task
            for task in self.tasks:
                task.downstream_list.append(other)
                other.upstream_list.append(task)
        return other

    def __rrshift__(self, other):
        # When Task >> TaskGroup or TaskGroup >> TaskGroup
        if isinstance(other, MockTaskGroup):
            # Connect all tasks in other to all tasks in self
            for other_task in other.tasks:
                for task in self.tasks:
                    other_task.downstream_list.append(task)
                    task.upstream_list.append(other_task)
            other.downstream_list.append(self)
            self.upstream_list.append(other)
        elif isinstance(other, MockOperator):
            # Connect other task to all tasks in self
            for task in self.tasks:
                other.downstream_list.append(task)
                task.upstream_list.append(other)
        return self


class MockOperator:
    """Mock for Airflow operators"""

    _all_tasks = []

    def __init__(self, task_id=None, job_name=None, script_location=None, sla=None,
                 execution_timeout=None, doc_md=None, **kwargs):
        self.task_id = task_id
        self.job_name = job_name
        self.script_location = script_location
        self.sla = sla
        self.execution_timeout = execution_timeout
        self.doc_md = doc_md
        self.upstream_list = []
        self.downstream_list = []
        self._kwargs = kwargs
        MockOperator._all_tasks.append(self)

        # If created inside a TaskGroup context, add to that group
        if MockTaskGroup._current_group is not None:
            MockTaskGroup._current_group.tasks.append(self)

    def __rshift__(self, other):
        if isinstance(other, list):
            for item in other:
                self.downstream_list.append(item)
                item.upstream_list.append(self)
            return other
        else:
            self.downstream_list.append(other)
            other.upstream_list.append(self)
            return other

    def __rrshift__(self, other):
        if isinstance(other, list):
            for item in other:
                item.downstream_list.append(self)
                self.upstream_list.append(item)
        else:
            other.downstream_list.append(self)
            self.upstream_list.append(other)
        return self


class MockDAG:
    """Mock for airflow.DAG"""

    _instance = None

    def __init__(self, dag_id, default_args=None, description=None, schedule_interval=None,
                 start_date=None, catchup=None, max_active_runs=None, tags=None,
                 sla_miss_callback=None, doc_md=None, **kwargs):
        self.dag_id = dag_id
        self.default_args = default_args or {}
        self.description = description
        self.schedule_interval = schedule_interval
        self.start_date = start_date
        self.catchup = catchup
        self.max_active_runs = max_active_runs
        self.tags = tags or []
        self.sla_miss_callback = sla_miss_callback
        self.doc_md = doc_md
        MockDAG._instance = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ============================================================================
# Setup Mocks and Load DAG
# ============================================================================

@pytest.fixture(scope="module", autouse=True)
def setup_mocks():
    """Setup mock Airflow modules before loading DAG"""
    # Create mock modules
    airflow_mock = types.ModuleType('airflow')
    models_mock = types.ModuleType('airflow.models')
    operators_mock = types.ModuleType('airflow.operators')
    dummy_mock = types.ModuleType('airflow.operators.dummy')
    python_mock = types.ModuleType('airflow.operators.python')
    providers_mock = types.ModuleType('airflow.providers')
    amazon_mock = types.ModuleType('airflow.providers.amazon')
    aws_mock = types.ModuleType('airflow.providers.amazon.aws')
    aws_operators_mock = types.ModuleType('airflow.providers.amazon.aws.operators')
    glue_mock = types.ModuleType('airflow.providers.amazon.aws.operators.glue')
    slack_mock = types.ModuleType('airflow.providers.slack')
    slack_operators_mock = types.ModuleType('airflow.providers.slack.operators')
    slack_webhook_mock = types.ModuleType('airflow.providers.slack.operators.slack_webhook')
    utils_mock = types.ModuleType('airflow.utils')
    task_group_mock = types.ModuleType('airflow.utils.task_group')

    # Assign mock classes
    models_mock.Variable = MockVariable
    models_mock.DAG = MockDAG
    airflow_mock.DAG = MockDAG  # Also expose DAG at top level for "from airflow import DAG"
    dummy_mock.DummyOperator = MockOperator
    python_mock.PythonOperator = MockOperator
    glue_mock.GlueJobOperator = MockOperator
    slack_webhook_mock.SlackWebhookOperator = MockOperator
    task_group_mock.TaskGroup = MockTaskGroup

    # Build module hierarchy
    airflow_mock.models = models_mock
    airflow_mock.operators = operators_mock
    operators_mock.dummy = dummy_mock
    operators_mock.python = python_mock
    airflow_mock.providers = providers_mock
    providers_mock.amazon = amazon_mock
    amazon_mock.aws = aws_mock
    aws_mock.operators = aws_operators_mock
    aws_operators_mock.glue = glue_mock
    providers_mock.slack = slack_mock
    slack_mock.operators = slack_operators_mock
    slack_operators_mock.slack_webhook = slack_webhook_mock
    airflow_mock.utils = utils_mock
    utils_mock.task_group = task_group_mock

    # Inject into sys.modules
    sys.modules['airflow'] = airflow_mock
    sys.modules['airflow.models'] = models_mock
    sys.modules['airflow.operators'] = operators_mock
    sys.modules['airflow.operators.dummy'] = dummy_mock
    sys.modules['airflow.operators.python'] = python_mock
    sys.modules['airflow.providers'] = providers_mock
    sys.modules['airflow.providers.amazon'] = amazon_mock
    sys.modules['airflow.providers.amazon.aws'] = aws_mock
    sys.modules['airflow.providers.amazon.aws.operators'] = aws_operators_mock
    sys.modules['airflow.providers.amazon.aws.operators.glue'] = glue_mock
    sys.modules['airflow.providers.slack'] = slack_mock
    sys.modules['airflow.providers.slack.operators'] = slack_operators_mock
    sys.modules['airflow.providers.slack.operators.slack_webhook'] = slack_webhook_mock
    sys.modules['airflow.utils'] = utils_mock
    sys.modules['airflow.utils.task_group'] = task_group_mock

    yield

    # Cleanup
    for module in list(sys.modules.keys()):
        if module.startswith('airflow'):
            del sys.modules[module]


@pytest.fixture(scope="module")
def dag_module(setup_mocks):
    """Load the DAG module"""
    # Clear previous state
    MockOperator._all_tasks = []
    MockTaskGroup._groups = {}
    MockDAG._instance = None

    # Load DAG file
    import importlib.util
    spec = importlib.util.spec_from_file_location("us_mutual_funds_etf_dag", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


@pytest.fixture
def dag(dag_module):
    """Get DAG instance"""
    return MockDAG._instance


@pytest.fixture
def all_tasks(dag_module):
    """Get all tasks"""
    return MockOperator._all_tasks


@pytest.fixture
def task_groups(dag_module):
    """Get all task groups"""
    return MockTaskGroup._groups


# ============================================================================
# Test DAG Load
# ============================================================================

def test_dag_file_exists():
    """Test that DAG file exists"""
    assert os.path.exists(DAG_FILE), f"DAG file not found: {DAG_FILE}"


def test_dag_is_valid_python():
    """Test DAG file is valid Python"""
    with open(DAG_FILE, 'r') as f:
        code = f.read()
    try:
        ast.parse(code)
    except SyntaxError as e:
        pytest.fail(f"DAG has syntax errors: {e}")


def test_dag_loads_without_errors(dag):
    """Test that DAG loads without errors"""
    assert dag is not None, "DAG failed to load"


# ============================================================================
# Test DAG Configuration
# ============================================================================

def test_dag_id(dag):
    """Test DAG has correct ID"""
    assert dag.dag_id == "us_mutual_funds_etf_pipeline"


def test_dag_schedule_interval(dag):
    """Test DAG schedule is monthly"""
    assert dag.schedule_interval == "0 2 1 * *"


def test_dag_start_date(dag):
    """Test DAG start_date is set"""
    assert dag.start_date == datetime(2025, 1, 1)


def test_dag_catchup_disabled(dag):
    """Test DAG has catchup=False"""
    assert dag.catchup is False


def test_dag_max_active_runs(dag):
    """Test DAG has max_active_runs=1"""
    assert dag.max_active_runs == 1


def test_dag_tags(dag):
    """Test DAG has required tags"""
    expected_tags = {"finance", "iceberg", "medallion", "funds"}
    assert expected_tags.issubset(set(dag.tags)), f"Missing tags. Expected {expected_tags}, got {dag.tags}"


def test_dag_description(dag):
    """Test DAG has a description"""
    assert dag.description is not None
    assert "Bronze" in dag.description and "Silver" in dag.description


def test_dag_doc_md(dag):
    """Test DAG has documentation"""
    assert dag.doc_md is not None
    assert len(dag.doc_md) > 100


# ============================================================================
# Test Default Args
# ============================================================================

def test_default_args_owner(dag):
    """Test default_args has owner"""
    assert dag.default_args.get("owner") == "data_engineering"


def test_default_args_retries(dag):
    """Test default_args has retries=3"""
    assert dag.default_args.get("retries") == 3


def test_default_args_retry_delay(dag):
    """Test default_args has retry_delay"""
    assert dag.default_args.get("retry_delay") == timedelta(minutes=5)


def test_default_args_exponential_backoff(dag):
    """Test default_args has exponential backoff enabled"""
    assert dag.default_args.get("retry_exponential_backoff") is True


def test_default_args_max_retry_delay(dag):
    """Test default_args has max_retry_delay"""
    assert dag.default_args.get("max_retry_delay") == timedelta(minutes=30)


def test_default_args_depends_on_past(dag):
    """Test default_args has depends_on_past=False"""
    assert dag.default_args.get("depends_on_past") is False


def test_default_args_email_on_failure(dag):
    """Test default_args has email_on_failure=True"""
    assert dag.default_args.get("email_on_failure") is True


def test_default_args_email_list(dag):
    """Test default_args has email list"""
    emails = dag.default_args.get("email")
    assert emails is not None and len(emails) > 0


def test_default_args_failure_callback(dag):
    """Test default_args has on_failure_callback"""
    assert dag.default_args.get("on_failure_callback") is not None


def test_dag_sla_miss_callback(dag):
    """Test DAG has sla_miss_callback"""
    assert dag.sla_miss_callback is not None


# ============================================================================
# Test Task Count
# ============================================================================

def test_task_count(all_tasks):
    """Test DAG has expected number of tasks"""
    # start + generate_bronze + 3 silver clean + silver_qg + 3 gold dims + gold_fact + gold_qg + end = 12
    assert len(all_tasks) == 12, f"Expected 12 tasks, got {len(all_tasks)}"


def test_task_groups_exist(task_groups):
    """Test TaskGroups exist"""
    expected_groups = ["bronze_zone", "silver_zone", "gold_zone"]
    for group in expected_groups:
        assert group in task_groups, f"TaskGroup {group} not found"


# ============================================================================
# Test Task Existence
# ============================================================================

def test_start_task_exists(all_tasks):
    """Test start task exists"""
    task_ids = [t.task_id for t in all_tasks]
    assert "start" in task_ids


def test_end_task_exists(all_tasks):
    """Test end task exists"""
    task_ids = [t.task_id for t in all_tasks]
    assert "end" in task_ids


def test_bronze_task_exists(all_tasks):
    """Test Bronze task exists"""
    task_ids = [t.task_id for t in all_tasks]
    assert "generate_bronze_data" in task_ids


def test_silver_tasks_exist(all_tasks):
    """Test Silver tasks exist"""
    task_ids = [t.task_id for t in all_tasks]
    silver_tasks = ["clean_funds", "clean_market_data", "clean_nav_prices", "quality_gate_silver"]
    for task_id in silver_tasks:
        assert task_id in task_ids, f"Task {task_id} not found"


def test_gold_tasks_exist(all_tasks):
    """Test Gold tasks exist"""
    task_ids = [t.task_id for t in all_tasks]
    gold_tasks = ["build_dim_fund", "build_dim_category", "build_dim_date",
                  "build_fact_fund_performance", "quality_gate_gold"]
    for task_id in gold_tasks:
        assert task_id in task_ids, f"Task {task_id} not found"


# ============================================================================
# Test Task Dependencies
# ============================================================================

def get_task_by_id(all_tasks, task_id):
    """Helper to get task by ID"""
    for task in all_tasks:
        if task.task_id == task_id:
            return task
    return None


def test_bronze_to_silver_dependency(all_tasks):
    """Test Bronze flows to Silver"""
    bronze = get_task_by_id(all_tasks, "generate_bronze_data")
    clean_funds = get_task_by_id(all_tasks, "clean_funds")
    clean_market = get_task_by_id(all_tasks, "clean_market_data")
    clean_nav = get_task_by_id(all_tasks, "clean_nav_prices")

    assert bronze in clean_funds.upstream_list
    assert bronze in clean_market.upstream_list
    assert bronze in clean_nav.upstream_list


def test_silver_cleaning_to_quality_gate(all_tasks):
    """Test Silver cleaning flows to quality gate"""
    clean_funds = get_task_by_id(all_tasks, "clean_funds")
    clean_market = get_task_by_id(all_tasks, "clean_market_data")
    clean_nav = get_task_by_id(all_tasks, "clean_nav_prices")
    quality_gate = get_task_by_id(all_tasks, "quality_gate_silver")

    assert clean_funds in quality_gate.upstream_list
    assert clean_market in quality_gate.upstream_list
    assert clean_nav in quality_gate.upstream_list


def test_silver_quality_gate_to_gold(all_tasks):
    """Test Silver quality gate blocks Gold"""
    quality_gate = get_task_by_id(all_tasks, "quality_gate_silver")
    build_dim_fund = get_task_by_id(all_tasks, "build_dim_fund")
    build_dim_category = get_task_by_id(all_tasks, "build_dim_category")
    build_dim_date = get_task_by_id(all_tasks, "build_dim_date")

    assert quality_gate in build_dim_fund.upstream_list
    assert quality_gate in build_dim_category.upstream_list
    assert quality_gate in build_dim_date.upstream_list


def test_gold_dims_to_fact(all_tasks):
    """Test Gold dimensions flow to fact"""
    build_dim_fund = get_task_by_id(all_tasks, "build_dim_fund")
    build_dim_category = get_task_by_id(all_tasks, "build_dim_category")
    build_dim_date = get_task_by_id(all_tasks, "build_dim_date")
    build_fact = get_task_by_id(all_tasks, "build_fact_fund_performance")

    assert build_dim_fund in build_fact.upstream_list
    assert build_dim_category in build_fact.upstream_list
    assert build_dim_date in build_fact.upstream_list


def test_gold_fact_to_quality_gate(all_tasks):
    """Test Gold fact flows to quality gate"""
    build_fact = get_task_by_id(all_tasks, "build_fact_fund_performance")
    quality_gate = get_task_by_id(all_tasks, "quality_gate_gold")

    assert build_fact in quality_gate.upstream_list


# ============================================================================
# Test SLA Configuration
# ============================================================================

def test_bronze_has_sla(all_tasks):
    """Test Bronze task has SLA"""
    bronze = get_task_by_id(all_tasks, "generate_bronze_data")
    assert bronze.sla is not None
    assert bronze.sla == timedelta(minutes=30)


def test_silver_cleaning_has_sla(all_tasks):
    """Test Silver cleaning tasks have SLA"""
    for task_id in ["clean_funds", "clean_market_data", "clean_nav_prices"]:
        task = get_task_by_id(all_tasks, task_id)
        assert task.sla is not None
        assert task.sla == timedelta(minutes=15)


def test_silver_quality_gate_has_sla(all_tasks):
    """Test Silver quality gate has SLA"""
    task = get_task_by_id(all_tasks, "quality_gate_silver")
    assert task.sla is not None
    assert task.sla == timedelta(minutes=10)


def test_gold_quality_gate_has_sla(all_tasks):
    """Test Gold quality gate has SLA"""
    task = get_task_by_id(all_tasks, "quality_gate_gold")
    assert task.sla is not None
    assert task.sla == timedelta(minutes=10)


# ============================================================================
# Test Task Documentation
# ============================================================================

def test_glue_tasks_have_doc_md(all_tasks):
    """Test Glue tasks have documentation"""
    glue_tasks = [t for t in all_tasks if t.job_name is not None]
    for task in glue_tasks:
        assert task.doc_md is not None, f"{task.task_id} missing doc_md"
        assert len(task.doc_md) > 50, f"{task.task_id} doc_md too short"


def test_all_tasks_have_execution_timeout(all_tasks):
    """Test tasks have execution timeout"""
    glue_tasks = [t for t in all_tasks if t.job_name is not None]
    for task in glue_tasks:
        assert task.execution_timeout is not None, f"{task.task_id} missing execution_timeout"


# ============================================================================
# Test Parallel Execution
# ============================================================================

def test_silver_cleaning_tasks_are_parallel(all_tasks):
    """Test Silver cleaning tasks can run in parallel"""
    clean_funds = get_task_by_id(all_tasks, "clean_funds")
    clean_market = get_task_by_id(all_tasks, "clean_market_data")
    clean_nav = get_task_by_id(all_tasks, "clean_nav_prices")

    # They should not be upstream/downstream of each other
    assert clean_market not in clean_funds.upstream_list
    assert clean_market not in clean_funds.downstream_list
    assert clean_nav not in clean_funds.upstream_list
    assert clean_nav not in clean_funds.downstream_list


def test_gold_dim_tasks_are_parallel(all_tasks):
    """Test Gold dimension tasks can run in parallel"""
    dim_fund = get_task_by_id(all_tasks, "build_dim_fund")
    dim_category = get_task_by_id(all_tasks, "build_dim_category")
    dim_date = get_task_by_id(all_tasks, "build_dim_date")

    # They should not be upstream/downstream of each other
    assert dim_category not in dim_fund.upstream_list
    assert dim_category not in dim_fund.downstream_list
    assert dim_date not in dim_fund.upstream_list


# ============================================================================
# Test Schedule YAML Consistency
# ============================================================================

def test_schedule_yaml_exists():
    """Test schedule.yaml exists"""
    assert os.path.exists(SCHEDULE_YAML), f"schedule.yaml not found: {SCHEDULE_YAML}"


def test_schedule_yaml_matches_dag(dag):
    """Test schedule.yaml matches DAG configuration"""
    with open(SCHEDULE_YAML, 'r') as f:
        schedule_config = yaml.safe_load(f)

    # Check workload name
    assert schedule_config['workload_name'] == 'us_mutual_funds_etf'

    # Check schedule frequency
    assert schedule_config['schedule']['cron_expression'] == dag.schedule_interval

    # Check execution settings
    assert schedule_config['execution']['catchup'] == dag.catchup
    assert schedule_config['execution']['max_active_runs'] == dag.max_active_runs


# ============================================================================
# Summary
# ============================================================================

def test_summary(dag, all_tasks, task_groups):
    """Print test summary"""
    print(f"\n{'='*70}")
    print(f"DAG Test Summary: {dag.dag_id}")
    print(f"{'='*70}")
    print(f"Total tasks: {len(all_tasks)}")
    print(f"Task groups: {len(task_groups)}")
    print(f"Schedule: {dag.schedule_interval}")
    print(f"Catchup: {dag.catchup}")
    print(f"Max active runs: {dag.max_active_runs}")
    print(f"Tags: {', '.join(dag.tags)}")
    print(f"{'='*70}\n")
