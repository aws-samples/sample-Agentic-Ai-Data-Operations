"""
Unit tests for DAG configuration files.

Tests schedule.yaml and analytics.yaml for validity and correctness.
"""

import pytest
import yaml
from pathlib import Path
from datetime import datetime
from croniter import croniter


class TestScheduleConfig:
    """Test schedule.yaml configuration"""

    @pytest.fixture
    def schedule_config(self):
        """Load schedule.yaml"""
        config_path = Path(__file__).parent.parent.parent / 'config' / 'schedule.yaml'
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def test_schedule_yaml_valid(self, schedule_config):
        """Test schedule.yaml is valid YAML"""
        assert schedule_config is not None
        assert isinstance(schedule_config, dict)

    def test_workload_name(self, schedule_config):
        """Test workload name is correct"""
        assert schedule_config['workload'] == 'financial_portfolios'

    def test_cron_schedule_valid(self, schedule_config):
        """Test cron schedule is valid"""
        cron = schedule_config['schedule']['cron']
        assert cron == '0 14 * * *'

        # Validate cron expression
        assert croniter.is_valid(cron)

        # Test cron runs daily at 14:00 UTC
        base = datetime(2026, 3, 20, 0, 0, 0)
        iter = croniter(cron, base)
        next_run = iter.get_next(datetime)
        assert next_run.hour == 14
        assert next_run.minute == 0

    def test_timezone_config(self, schedule_config):
        """Test timezone is US/Eastern"""
        assert schedule_config['schedule']['timezone'] == 'US/Eastern'

    def test_dag_config_present(self, schedule_config):
        """Test DAG configuration is present"""
        dag_config = schedule_config['dag_config']
        assert dag_config is not None
        assert dag_config['dag_id'] == 'financial_portfolios_pipeline'
        assert 'finance' in dag_config['tags']
        assert 'portfolios' in dag_config['tags']
        assert 'sox-compliant' in dag_config['tags']

    def test_retry_configuration(self, schedule_config):
        """Test retry configuration"""
        default_args = schedule_config['dag_config']['default_args']
        assert default_args['retries'] == 3
        assert default_args['retry_delay_minutes'] == 5
        assert default_args['retry_exponential_backoff'] is True
        assert default_args['max_retry_delay_minutes'] == 30

    def test_sla_configuration(self, schedule_config):
        """Test SLA is configured (30 minutes)"""
        default_args = schedule_config['dag_config']['default_args']
        assert default_args['sla_minutes'] == 30

    def test_failure_callbacks_configured(self, schedule_config):
        """Test failure callbacks are configured"""
        callbacks = schedule_config['failure_callbacks']
        assert callbacks is not None
        assert 'on_failure' in callbacks
        assert 'on_sox_compliance_failure' in callbacks
        assert 'email' in callbacks['on_failure']['notification_channels']
        assert 'compliance@company.com' in callbacks['on_sox_compliance_failure']['recipients']

    def test_task_groups_defined(self, schedule_config):
        """Test all required task groups are defined"""
        task_groups = schedule_config['task_groups']
        group_names = [tg['name'] for tg in task_groups]

        expected_groups = [
            'bronze_ingestion',
            'silver_transformation',
            'silver_quality_gate',
            'gold_transformation',
            'gold_quality_gate',
            'dashboard_refresh'
        ]

        for expected in expected_groups:
            assert expected in group_names, f"Missing task group: {expected}"

    def test_quality_gates_present(self, schedule_config):
        """Test quality gates are marked as gates"""
        task_groups = {tg['name']: tg for tg in schedule_config['task_groups']}

        assert task_groups['silver_quality_gate'].get('gate') is True
        assert task_groups['gold_quality_gate'].get('gate') is True

    def test_bronze_ingestion_tasks(self, schedule_config):
        """Test bronze ingestion has all 3 tables"""
        bronze_group = next(tg for tg in schedule_config['task_groups'] if tg['name'] == 'bronze_ingestion')
        tasks = bronze_group['tasks']

        assert 'ingest_stocks' in tasks
        assert 'ingest_portfolios' in tasks
        assert 'ingest_positions' in tasks

    def test_gold_transformation_tasks(self, schedule_config):
        """Test gold transformation has star schema tasks"""
        gold_group = next(tg for tg in schedule_config['task_groups'] if tg['name'] == 'gold_transformation')
        tasks = gold_group['tasks']

        assert 'transform_dim_stocks' in tasks
        assert 'transform_dim_portfolios' in tasks
        assert 'transform_fact_positions' in tasks
        assert 'transform_portfolio_summary' in tasks

    def test_catchup_disabled(self, schedule_config):
        """Test catchup is disabled"""
        assert schedule_config['schedule']['catchup'] is False

    def test_max_active_runs(self, schedule_config):
        """Test max_active_runs is 1"""
        assert schedule_config['schedule']['max_active_runs'] == 1


class TestAnalyticsConfig:
    """Test analytics.yaml configuration"""

    @pytest.fixture
    def analytics_config(self):
        """Load analytics.yaml"""
        config_path = Path(__file__).parent.parent.parent / 'config' / 'analytics.yaml'
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def test_analytics_yaml_valid(self, analytics_config):
        """Test analytics.yaml is valid YAML"""
        assert analytics_config is not None
        assert isinstance(analytics_config, dict)

    def test_workload_name(self, analytics_config):
        """Test workload name is correct"""
        assert analytics_config['workload'] == 'financial_portfolios'

    def test_platform_is_quicksight(self, analytics_config):
        """Test platform is Amazon QuickSight"""
        assert analytics_config['platform'] == 'amazon_quicksight'

    def test_dashboard_defined(self, analytics_config):
        """Test dashboard is defined"""
        dashboards = analytics_config['dashboards']
        assert len(dashboards) == 1

        dashboard = dashboards[0]
        assert dashboard['dashboard_id'] == 'portfolio_performance'
        assert dashboard['name'] == 'Portfolio Performance Dashboard'

    def test_datasets_defined(self, analytics_config):
        """Test all required datasets are defined"""
        dashboard = analytics_config['dashboards'][0]
        datasets = dashboard['datasets']

        dataset_ids = [ds['dataset_id'] for ds in datasets]
        expected_datasets = ['fact_positions', 'dim_stocks', 'dim_portfolios', 'portfolio_summary']

        for expected in expected_datasets:
            assert expected in dataset_ids, f"Missing dataset: {expected}"

    def test_dataset_sources(self, analytics_config):
        """Test dataset sources reference gold zone tables"""
        dashboard = analytics_config['dashboards'][0]
        datasets = dashboard['datasets']

        for dataset in datasets:
            assert dataset['source'].startswith('gold.'), f"Dataset {dataset['dataset_id']} not in gold zone"

    def test_visuals_defined(self, analytics_config):
        """Test all 4 required visuals are defined"""
        dashboard = analytics_config['dashboards'][0]
        visuals = dashboard['visuals']

        assert len(visuals) == 4

        visual_ids = [v['visual_id'] for v in visuals]
        expected_visuals = [
            'top_positions_by_gain',
            'recent_trades',
            'portfolio_performance_by_manager',
            'sector_allocation'
        ]

        for expected in expected_visuals:
            assert expected in visual_ids, f"Missing visual: {expected}"

    def test_top_positions_visual(self, analytics_config):
        """Test top positions by gain visual"""
        dashboard = analytics_config['dashboards'][0]
        visual = next(v for v in dashboard['visuals'] if v['visual_id'] == 'top_positions_by_gain')

        assert visual['type'] == 'bar_chart'
        assert visual['dataset'] == 'fact_positions'
        assert 'unrealized_gain_loss' in visual['query']['select']
        assert visual['query']['limit'] == 5

    def test_recent_trades_visual(self, analytics_config):
        """Test recent trades visual"""
        dashboard = analytics_config['dashboards'][0]
        visual = next(v for v in dashboard['visuals'] if v['visual_id'] == 'recent_trades')

        assert visual['type'] == 'table'
        assert visual['dataset'] == 'fact_positions'
        assert visual['query']['order_by'] == 'entry_date DESC'
        assert visual['query']['limit'] == 5
        assert len(visual['columns']) == 6

    def test_portfolio_performance_visual(self, analytics_config):
        """Test portfolio performance by manager visual"""
        dashboard = analytics_config['dashboards'][0]
        visual = next(v for v in dashboard['visuals'] if v['visual_id'] == 'portfolio_performance_by_manager')

        assert visual['type'] == 'bar_chart'
        assert visual['dataset'] == 'portfolio_summary'
        assert len(visual['joins']) == 1
        assert 'manager_name' in visual['query']['group_by']

    def test_sector_allocation_visual(self, analytics_config):
        """Test sector allocation visual"""
        dashboard = analytics_config['dashboards'][0]
        visual = next(v for v in dashboard['visuals'] if v['visual_id'] == 'sector_allocation')

        assert visual['type'] == 'pie_chart'
        assert visual['labels'] is True
        assert visual['percentages'] is True
        assert 'sector' in visual['dimension']

    def test_filters_defined(self, analytics_config):
        """Test dashboard filters are defined"""
        dashboard = analytics_config['dashboards'][0]
        filters = dashboard['filters']

        assert len(filters) == 2

        filter_ids = [f['filter_id'] for f in filters]
        assert 'date_range' in filter_ids
        assert 'portfolio_filter' in filter_ids

    def test_refresh_schedule(self, analytics_config):
        """Test dashboard refresh schedule"""
        dashboard = analytics_config['dashboards'][0]
        refresh = dashboard['refresh_schedule']

        assert refresh['frequency'] == 'daily'
        assert refresh['time'] == '15:00'
        assert refresh['timezone'] == 'US/Eastern'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
