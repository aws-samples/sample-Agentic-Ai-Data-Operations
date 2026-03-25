"""
Integration tests for financial_portfolios DAG.

Tests DAG structure, task dependencies, and execution flow.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime
from airflow.models import DagBag, Variable
from airflow.utils.task_group import TaskGroup


class TestDAGIntegration:
    """Integration tests for DAG structure and execution"""

    @pytest.fixture(scope='class')
    def dagbag(self):
        """Load DAG from file"""
        dag_dir = Path(__file__).parent.parent.parent / 'dags'
        dagbag = DagBag(dag_folder=str(dag_dir), include_examples=False)
        return dagbag

    @pytest.fixture(scope='class')
    def dag(self, dagbag):
        """Get the financial_portfolios_pipeline DAG"""
        dag_id = 'financial_portfolios_pipeline'
        assert dag_id in dagbag.dags, f"DAG {dag_id} not found in DagBag"
        return dagbag.dags[dag_id]

    def test_dag_loads_without_errors(self, dagbag):
        """Test DAG can be loaded without import errors"""
        assert len(dagbag.import_errors) == 0, f"DAG import errors: {dagbag.import_errors}"

    def test_dag_exists(self, dag):
        """Test DAG object exists"""
        assert dag is not None
        assert dag.dag_id == 'financial_portfolios_pipeline'

    def test_dag_has_correct_schedule(self, dag):
        """Test DAG has correct schedule interval"""
        assert dag.schedule_interval == '0 14 * * *'

    def test_dag_has_correct_tags(self, dag):
        """Test DAG has required tags"""
        assert 'finance' in dag.tags
        assert 'portfolios' in dag.tags
        assert 'sox-compliant' in dag.tags

    def test_catchup_disabled(self, dag):
        """Test catchup is disabled"""
        assert dag.catchup is False

    def test_max_active_runs(self, dag):
        """Test max_active_runs is 1"""
        assert dag.max_active_runs == 1

    def test_dag_has_description(self, dag):
        """Test DAG has description"""
        assert dag.description is not None
        assert len(dag.description) > 0

    def test_dag_has_doc_md(self, dag):
        """Test DAG has documentation"""
        assert dag.doc_md is not None

    def test_failure_callback_configured(self, dag):
        """Test failure callback is configured"""
        assert dag.default_args.get('on_failure_callback') is not None

    def test_task_groups_used(self, dag):
        """Test DAG uses TaskGroups (not SubDagOperator)"""
        # Check for TaskGroup instances in the DAG
        task_groups = [task for task in dag.task_dict.values() if isinstance(task, TaskGroup)]

        # DAG should have task groups for bronze, silver, gold
        group_ids = [tg.group_id for tg in dag.task_group_dict.values() if tg.group_id]

        expected_groups = [
            'bronze_ingestion',
            'silver_transformation',
            'gold_transformation'
        ]

        for expected in expected_groups:
            assert expected in group_ids, f"Missing TaskGroup: {expected}"

    def test_no_subdag_operators(self, dag):
        """Test no SubDagOperator is used"""
        from airflow.operators.subdag import SubDagOperator

        for task in dag.tasks:
            assert not isinstance(task, SubDagOperator), f"SubDagOperator found: {task.task_id}"

    def test_bronze_ingestion_tasks(self, dag):
        """Test bronze ingestion tasks exist"""
        expected_tasks = [
            'bronze_ingestion.ingest_stocks',
            'bronze_ingestion.ingest_portfolios',
            'bronze_ingestion.ingest_positions'
        ]

        for task_id in expected_tasks:
            assert task_id in dag.task_dict, f"Missing task: {task_id}"

    def test_silver_transformation_tasks(self, dag):
        """Test silver transformation tasks exist"""
        expected_tasks = [
            'silver_transformation.transform_stocks_to_silver',
            'silver_transformation.transform_portfolios_to_silver',
            'silver_transformation.transform_positions_to_silver'
        ]

        for task_id in expected_tasks:
            assert task_id in dag.task_dict, f"Missing task: {task_id}"

    def test_quality_gate_tasks(self, dag):
        """Test quality gate tasks exist"""
        assert 'quality_check_silver' in dag.task_dict
        assert 'quality_check_gold' in dag.task_dict

    def test_gold_transformation_tasks(self, dag):
        """Test gold transformation tasks exist"""
        expected_tasks = [
            'gold_transformation.transform_dim_stocks',
            'gold_transformation.transform_dim_portfolios',
            'gold_transformation.transform_fact_positions',
            'gold_transformation.transform_portfolio_summary'
        ]

        for task_id in expected_tasks:
            assert task_id in dag.task_dict, f"Missing task: {task_id}"

    def test_dashboard_refresh_task(self, dag):
        """Test dashboard refresh task exists"""
        assert 'refresh_quicksight_datasets' in dag.task_dict

    def test_task_dependencies_bronze_to_silver(self, dag):
        """Test bronze tasks lead to silver tasks"""
        bronze_tasks = [
            dag.task_dict['bronze_ingestion.ingest_stocks'],
            dag.task_dict['bronze_ingestion.ingest_portfolios'],
            dag.task_dict['bronze_ingestion.ingest_positions']
        ]

        silver_tasks = [
            dag.task_dict['silver_transformation.transform_stocks_to_silver'],
            dag.task_dict['silver_transformation.transform_portfolios_to_silver'],
            dag.task_dict['silver_transformation.transform_positions_to_silver']
        ]

        # All bronze tasks should be upstream of at least one silver task
        for bronze_task in bronze_tasks:
            downstream_ids = [t.task_id for t in bronze_task.get_flat_relatives(upstream=False)]
            assert any(silver_task.task_id in downstream_ids for silver_task in silver_tasks)

    def test_task_dependencies_silver_to_quality_gate(self, dag):
        """Test silver tasks lead to silver quality gate"""
        silver_tasks = [
            dag.task_dict['silver_transformation.transform_stocks_to_silver'],
            dag.task_dict['silver_transformation.transform_portfolios_to_silver'],
            dag.task_dict['silver_transformation.transform_positions_to_silver']
        ]

        quality_gate = dag.task_dict['quality_check_silver']

        # All silver tasks should be upstream of quality gate
        for silver_task in silver_tasks:
            downstream_ids = [t.task_id for t in silver_task.get_flat_relatives(upstream=False)]
            assert 'quality_check_silver' in downstream_ids

    def test_task_dependencies_quality_gate_to_gold(self, dag):
        """Test silver quality gate leads to gold transformation"""
        quality_gate = dag.task_dict['quality_check_silver']

        gold_tasks = [
            'gold_transformation.transform_dim_stocks',
            'gold_transformation.transform_dim_portfolios',
            'gold_transformation.transform_fact_positions',
            'gold_transformation.transform_portfolio_summary'
        ]

        downstream_ids = [t.task_id for t in quality_gate.get_flat_relatives(upstream=False)]

        # Quality gate should be upstream of at least one gold task
        assert any(gold_task in downstream_ids for gold_task in gold_tasks)

    def test_task_dependencies_gold_to_quality_gate(self, dag):
        """Test gold tasks lead to gold quality gate"""
        gold_tasks = [
            dag.task_dict['gold_transformation.transform_dim_stocks'],
            dag.task_dict['gold_transformation.transform_dim_portfolios'],
            dag.task_dict['gold_transformation.transform_fact_positions'],
            dag.task_dict['gold_transformation.transform_portfolio_summary']
        ]

        quality_gate = dag.task_dict['quality_check_gold']

        # All gold tasks should be upstream of quality gate
        for gold_task in gold_tasks:
            downstream_ids = [t.task_id for t in gold_task.get_flat_relatives(upstream=False)]
            assert 'quality_check_gold' in downstream_ids

    def test_task_dependencies_quality_gate_to_dashboard(self, dag):
        """Test gold quality gate leads to dashboard refresh"""
        quality_gate = dag.task_dict['quality_check_gold']
        dashboard_task = dag.task_dict['refresh_quicksight_datasets']

        downstream_ids = [t.task_id for t in quality_gate.get_flat_relatives(upstream=False)]
        assert 'refresh_quicksight_datasets' in downstream_ids

    def test_gold_star_schema_dependencies(self, dag):
        """Test star schema dependencies: dimensions before facts"""
        dim_stocks = dag.task_dict['gold_transformation.transform_dim_stocks']
        dim_portfolios = dag.task_dict['gold_transformation.transform_dim_portfolios']
        fact_positions = dag.task_dict['gold_transformation.transform_fact_positions']
        summary = dag.task_dict['gold_transformation.transform_portfolio_summary']

        # Dimensions should be upstream of fact
        fact_upstream = [t.task_id for t in fact_positions.get_flat_relatives(upstream=True)]
        assert 'gold_transformation.transform_dim_stocks' in fact_upstream
        assert 'gold_transformation.transform_dim_portfolios' in fact_upstream

        # Fact should be upstream of summary
        summary_upstream = [t.task_id for t in summary.get_flat_relatives(upstream=True)]
        assert 'gold_transformation.transform_fact_positions' in summary_upstream

    def test_no_hardcoded_credentials(self, dag):
        """Test no hardcoded credentials in DAG"""
        import inspect

        dag_file = Path(__file__).parent.parent.parent / 'dags' / 'financial_portfolios_dag.py'
        with open(dag_file, 'r') as f:
            content = f.read()

        # Check for common credential patterns
        forbidden_patterns = [
            'password=',
            'secret=',
            'aws_access_key_id=',
            'aws_secret_access_key=',
            'api_key='
        ]

        for pattern in forbidden_patterns:
            assert pattern.lower() not in content.lower(), f"Hardcoded credential pattern found: {pattern}"

    def test_uses_airflow_variables(self, dag):
        """Test DAG uses Airflow Variables for configuration"""
        import inspect

        dag_file = Path(__file__).parent.parent.parent / 'dags' / 'financial_portfolios_dag.py'
        with open(dag_file, 'r') as f:
            content = f.read()

        # Should use Variable.get() for configuration
        assert 'Variable.get(' in content

    def test_retry_configuration(self, dag):
        """Test tasks have retry configuration"""
        for task in dag.tasks:
            if task.task_id != 'refresh_quicksight_datasets':  # Dashboard refresh may have different config
                assert task.retries >= 3 or dag.default_args.get('retries') >= 3

    def test_sla_on_quality_gates(self, dag):
        """Test SLA is set on quality gate tasks"""
        quality_gates = [
            dag.task_dict['quality_check_silver'],
            dag.task_dict['quality_check_gold']
        ]

        for gate in quality_gates:
            # SLA should be set either on task or in default_args
            assert gate.sla is not None or dag.default_args.get('sla') is not None

    def test_dag_can_be_parsed(self, dagbag):
        """Test DAG can be successfully parsed by Airflow"""
        assert len(dagbag.dags) > 0
        assert 'financial_portfolios_pipeline' in dagbag.dags


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
