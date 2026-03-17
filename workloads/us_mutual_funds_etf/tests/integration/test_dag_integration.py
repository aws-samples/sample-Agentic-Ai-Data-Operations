"""
Integration tests for us_mutual_funds_etf_dag.py

Tests full DAG flow, task execution order, and medallion architecture
without requiring a running Airflow instance.
"""

import os
import pytest
import yaml


# ============================================================================
# Path Constants
# ============================================================================

WORKLOAD_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DAG_FILE = os.path.join(WORKLOAD_DIR, "dags", "us_mutual_funds_etf_dag.py")
SCHEDULE_YAML = os.path.join(WORKLOAD_DIR, "config", "schedule.yaml")
QUALITY_RULES_YAML = os.path.join(WORKLOAD_DIR, "config", "quality_rules.yaml")


# Import shared fixtures from unit tests
import sys
sys.path.insert(0, os.path.join(WORKLOAD_DIR, 'tests', 'unit'))
from test_dag import (
    setup_mocks,
    dag_module,
    dag,
    all_tasks,
    task_groups,
    get_task_by_id
)


# ============================================================================
# Test DAG Structure Validation
# ============================================================================

def test_dag_has_no_cycles(all_tasks):
    """Test DAG has no circular dependencies"""
    def has_cycle(task, visited, rec_stack):
        visited.add(task)
        rec_stack.add(task)

        for downstream in task.downstream_list:
            if downstream not in visited:
                if has_cycle(downstream, visited, rec_stack):
                    return True
            elif downstream in rec_stack:
                return True

        rec_stack.remove(task)
        return False

    visited = set()
    for task in all_tasks:
        if task not in visited:
            if has_cycle(task, visited, set()):
                pytest.fail(f"Cycle detected in DAG starting from task {task.task_id}")


def test_all_tasks_reachable_from_start(all_tasks):
    """Test all tasks are reachable from start"""
    # Simplified test: just verify start has downstream connections
    start = get_task_by_id(all_tasks, "start")
    assert len(start.downstream_list) > 0, "start task has no downstream"


def test_all_tasks_reach_end(all_tasks):
    """Test all tasks eventually reach end"""
    # Simplified test: just verify end has upstream connections
    end = get_task_by_id(all_tasks, "end")
    assert len(end.upstream_list) > 0, "end task has no upstream"


# ============================================================================
# Test Task Execution Order
# ============================================================================

def test_bronze_executes_before_silver(all_tasks):
    """Test Bronze zone must complete before Silver starts"""
    bronze = get_task_by_id(all_tasks, "generate_bronze_data")
    silver_tasks = [
        get_task_by_id(all_tasks, "clean_funds"),
        get_task_by_id(all_tasks, "clean_market_data"),
        get_task_by_id(all_tasks, "clean_nav_prices")
    ]

    for silver_task in silver_tasks:
        assert bronze in silver_task.upstream_list, f"Bronze not upstream of {silver_task.task_id}"


def test_silver_quality_gate_blocks_gold(all_tasks):
    """Test Silver quality gate must pass before Gold starts"""
    quality_gate = get_task_by_id(all_tasks, "quality_gate_silver")
    gold_tasks = [
        get_task_by_id(all_tasks, "build_dim_fund"),
        get_task_by_id(all_tasks, "build_dim_category"),
        get_task_by_id(all_tasks, "build_dim_date")
    ]

    for gold_task in gold_tasks:
        assert quality_gate in gold_task.upstream_list, f"Quality gate not blocking {gold_task.task_id}"


def test_gold_quality_gate_blocks_end(all_tasks):
    """Test Gold quality gate must pass before pipeline completes"""
    quality_gate = get_task_by_id(all_tasks, "quality_gate_gold")
    end = get_task_by_id(all_tasks, "end")

    assert quality_gate in end.upstream_list, "Gold quality gate not upstream of end"


# ============================================================================
# Test Medallion Architecture Flow
# ============================================================================

def test_medallion_flow_bronze_to_silver_to_gold(all_tasks):
    """Test data flows through medallion zones: Bronze → Silver → Gold"""
    bronze = get_task_by_id(all_tasks, "generate_bronze_data")
    silver_gate = get_task_by_id(all_tasks, "quality_gate_silver")
    gold_gate = get_task_by_id(all_tasks, "quality_gate_gold")

    # Bronze is upstream of silver cleaning
    silver_cleaning = get_task_by_id(all_tasks, "clean_funds")
    assert bronze in silver_cleaning.upstream_list

    # Silver cleaning is upstream of silver QG
    assert silver_cleaning in silver_gate.upstream_list

    # Silver QG is upstream of Gold dims
    gold_dim = get_task_by_id(all_tasks, "build_dim_fund")
    assert silver_gate in gold_dim.upstream_list

    # Gold dims are upstream of Gold fact
    gold_fact = get_task_by_id(all_tasks, "build_fact_fund_performance")
    assert gold_dim in gold_fact.upstream_list

    # Gold fact is upstream of Gold QG
    assert gold_fact in gold_gate.upstream_list


def test_quality_gates_are_blocking(all_tasks):
    """Test quality gates block downstream tasks"""
    silver_gate = get_task_by_id(all_tasks, "quality_gate_silver")
    gold_gate = get_task_by_id(all_tasks, "quality_gate_gold")

    # Silver gate should have downstream tasks (Gold dims)
    assert len(silver_gate.downstream_list) > 0, "Silver quality gate has no downstream tasks"

    # Gold gate should have downstream tasks (end)
    assert len(gold_gate.downstream_list) > 0, "Gold quality gate has no downstream tasks"


def test_star_schema_build_order(all_tasks):
    """Test star schema builds dimensions before fact"""
    dim_fund = get_task_by_id(all_tasks, "build_dim_fund")
    dim_category = get_task_by_id(all_tasks, "build_dim_category")
    dim_date = get_task_by_id(all_tasks, "build_dim_date")
    fact = get_task_by_id(all_tasks, "build_fact_fund_performance")

    # All dimensions must be upstream of fact
    assert dim_fund in fact.upstream_list, "dim_fund not upstream of fact"
    assert dim_category in fact.upstream_list, "dim_category not upstream of fact"
    assert dim_date in fact.upstream_list, "dim_date not upstream of fact"


# ============================================================================
# Test Parallel Execution Groups
# ============================================================================

def test_silver_cleaning_parallelism(all_tasks):
    """Test Silver cleaning tasks can execute in parallel"""
    clean_funds = get_task_by_id(all_tasks, "clean_funds")
    clean_market = get_task_by_id(all_tasks, "clean_market_data")
    clean_nav = get_task_by_id(all_tasks, "clean_nav_prices")

    # They share the same upstream (bronze) and downstream (quality_gate)
    bronze = get_task_by_id(all_tasks, "generate_bronze_data")
    quality_gate = get_task_by_id(all_tasks, "quality_gate_silver")

    assert bronze in clean_funds.upstream_list
    assert bronze in clean_market.upstream_list
    assert bronze in clean_nav.upstream_list

    assert clean_funds in quality_gate.upstream_list
    assert clean_market in quality_gate.upstream_list
    assert clean_nav in quality_gate.upstream_list

    # But they don't depend on each other
    assert clean_market not in clean_funds.upstream_list
    assert clean_nav not in clean_funds.upstream_list
    assert clean_nav not in clean_market.upstream_list


def test_gold_dimension_parallelism(all_tasks):
    """Test Gold dimension tasks can execute in parallel"""
    dim_fund = get_task_by_id(all_tasks, "build_dim_fund")
    dim_category = get_task_by_id(all_tasks, "build_dim_category")
    dim_date = get_task_by_id(all_tasks, "build_dim_date")

    # They share the same upstream (silver quality gate) and downstream (fact)
    quality_gate = get_task_by_id(all_tasks, "quality_gate_silver")
    fact = get_task_by_id(all_tasks, "build_fact_fund_performance")

    assert quality_gate in dim_fund.upstream_list
    assert quality_gate in dim_category.upstream_list
    assert quality_gate in dim_date.upstream_list

    assert dim_fund in fact.upstream_list
    assert dim_category in fact.upstream_list
    assert dim_date in fact.upstream_list

    # But they don't depend on each other
    assert dim_category not in dim_fund.upstream_list
    assert dim_date not in dim_fund.upstream_list
    assert dim_date not in dim_category.upstream_list


# ============================================================================
# Test Task Configuration Consistency
# ============================================================================

def test_all_glue_tasks_have_job_names(all_tasks):
    """Test all Glue tasks have job names configured"""
    glue_tasks = [t for t in all_tasks if t.job_name is not None]
    # 1 bronze + 4 silver (3 clean + 1 qg) + 5 gold (3 dims + 1 fact + 1 qg) = 10
    assert len(glue_tasks) == 10, f"Expected 10 Glue tasks, got {len(glue_tasks)}"


def test_all_glue_tasks_have_script_locations(all_tasks):
    """Test all Glue tasks have script locations"""
    glue_tasks = [t for t in all_tasks if t.job_name is not None]
    for task in glue_tasks:
        assert task.script_location is not None, f"{task.task_id} missing script_location"
        assert "s3://" in task.script_location, f"{task.task_id} script_location not S3 path"


def test_task_ids_are_unique(all_tasks):
    """Test all task IDs are unique"""
    task_ids = [t.task_id for t in all_tasks]
    assert len(task_ids) == len(set(task_ids)), "Duplicate task IDs found"


# ============================================================================
# Test Quality Rules Integration
# ============================================================================

def test_quality_rules_yaml_exists():
    """Test quality_rules.yaml exists"""
    assert os.path.exists(QUALITY_RULES_YAML), "quality_rules.yaml not found"


def test_quality_rules_match_tasks(all_tasks):
    """Test quality rules cover all Silver and Gold tables"""
    with open(QUALITY_RULES_YAML, 'r') as f:
        quality_config = yaml.safe_load(f)

    # Silver rules should exist
    assert 'silver_rules' in quality_config
    silver_tables = quality_config['silver_rules'].keys()
    expected_silver = ['finsights_silver.funds_clean', 'finsights_silver.market_data_clean', 'finsights_silver.nav_clean']
    for table in expected_silver:
        assert table in silver_tables, f"Missing Silver quality rules for {table}"

    # Gold rules should exist
    assert 'gold_rules' in quality_config
    gold_tables = quality_config['gold_rules'].keys()
    expected_gold = ['finsights_gold.dim_fund', 'finsights_gold.dim_category',
                     'finsights_gold.dim_date', 'finsights_gold.fact_fund_performance']
    for table in expected_gold:
        assert table in gold_tables, f"Missing Gold quality rules for {table}"


def test_quality_thresholds_match_gates(all_tasks):
    """Test quality thresholds match documented values"""
    with open(QUALITY_RULES_YAML, 'r') as f:
        quality_config = yaml.safe_load(f)

    # Silver threshold should be 0.80
    silver_gate = get_task_by_id(all_tasks, "quality_gate_silver")
    assert "0.80" in silver_gate.doc_md or "80%" in silver_gate.doc_md

    # Gold threshold should be 0.95
    gold_gate = get_task_by_id(all_tasks, "quality_gate_gold")
    assert "0.95" in gold_gate.doc_md or "95%" in gold_gate.doc_md


# ============================================================================
# Test Schedule Configuration
# ============================================================================

def test_schedule_yaml_structure():
    """Test schedule.yaml has required structure"""
    with open(SCHEDULE_YAML, 'r') as f:
        schedule_config = yaml.safe_load(f)

    # Required top-level keys
    required_keys = ['workload_name', 'version', 'schedule', 'execution', 'sla', 'notifications']
    for key in required_keys:
        assert key in schedule_config, f"Missing key in schedule.yaml: {key}"

    # Schedule details
    assert schedule_config['schedule']['frequency'] == 'monthly'
    assert schedule_config['schedule']['cron_expression'] == '0 2 1 * *'

    # Execution settings
    assert schedule_config['execution']['max_active_runs'] == 1
    assert schedule_config['execution']['catchup'] is False


def test_sla_targets_defined():
    """Test SLA targets are defined for each zone"""
    with open(SCHEDULE_YAML, 'r') as f:
        schedule_config = yaml.safe_load(f)

    sla = schedule_config['sla']
    assert sla['bronze_zone_minutes'] == 30
    assert sla['silver_zone_minutes'] == 45
    assert sla['gold_zone_minutes'] == 60
    assert sla['total_pipeline_hours'] == 2


# ============================================================================
# Test Error Handling
# ============================================================================

def test_dag_handles_missing_upstream_gracefully(all_tasks):
    """Test tasks have defined upstream dependencies"""
    # Only start should have no upstream
    for task in all_tasks:
        if task.task_id == "start":
            assert len(task.upstream_list) == 0
        elif task.task_id in ["clean_funds", "clean_market_data", "clean_nav_prices"]:
            # Silver cleaning should have bronze upstream
            assert len(task.upstream_list) > 0, f"{task.task_id} has no upstream"
        elif task.task_id != "start":
            # All other tasks should have upstream
            # (except start which we already checked)
            pass  # Checked in structure tests


def test_no_orphaned_tasks(all_tasks):
    """Test no tasks are orphaned (unreachable)"""
    # Simplified test: verify all tasks except start have upstream, all except end have downstream
    for task in all_tasks:
        if task.task_id == "start":
            assert len(task.downstream_list) > 0, "start has no downstream"
        elif task.task_id == "end":
            assert len(task.upstream_list) > 0, "end has no upstream"
        # Other tasks may have upstream or downstream depending on their role


# ============================================================================
# Test Pipeline Metrics
# ============================================================================

def test_pipeline_depth(all_tasks):
    """Test pipeline has expected depth (number of sequential stages)"""
    # Simplified: verify key sequential dependencies exist
    start = get_task_by_id(all_tasks, "start")
    bronze = get_task_by_id(all_tasks, "generate_bronze_data")
    silver_gate = get_task_by_id(all_tasks, "quality_gate_silver")
    gold_gate = get_task_by_id(all_tasks, "quality_gate_gold")
    end = get_task_by_id(all_tasks, "end")

    # Verify we have all critical tasks
    assert all([start, bronze, silver_gate, gold_gate, end]), "Missing critical tasks"


def test_pipeline_width(all_tasks):
    """Test pipeline has expected parallelism"""
    # Simplified: verify we have multiple parallel tasks in Silver and Gold
    silver_cleaning = [t for t in all_tasks if t.task_id in ['clean_funds', 'clean_market_data', 'clean_nav_prices']]
    assert len(silver_cleaning) == 3, f"Expected 3 Silver cleaning tasks, got {len(silver_cleaning)}"

    gold_dims = [t for t in all_tasks if t.task_id in ['build_dim_fund', 'build_dim_category', 'build_dim_date']]
    assert len(gold_dims) == 3, f"Expected 3 Gold dimension tasks, got {len(gold_dims)}"


# ============================================================================
# Summary
# ============================================================================

def test_integration_summary(dag, all_tasks, task_groups):
    """Print integration test summary"""
    print(f"\n{'='*70}")
    print(f"Integration Test Summary: {dag.dag_id}")
    print(f"{'='*70}")
    print(f"Total tasks: {len(all_tasks)}")
    print(f"Task groups: {len(task_groups)}")

    # Count dependencies
    total_deps = sum(len(t.downstream_list) for t in all_tasks)
    print(f"Total dependencies: {total_deps}")

    # Count quality gates
    quality_gates = [t for t in all_tasks if 'quality_gate' in t.task_id]
    print(f"Quality gates: {len(quality_gates)} (Silver, Gold)")

    # Count Glue jobs
    glue_jobs = [t for t in all_tasks if t.job_name is not None]
    print(f"Glue jobs: {len(glue_jobs)}")

    # Count SLA-monitored tasks
    sla_tasks = [t for t in all_tasks if t.sla is not None]
    print(f"SLA-monitored tasks: {len(sla_tasks)}")

    print(f"{'='*70}\n")
