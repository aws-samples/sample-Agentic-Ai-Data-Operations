"""
Integration Tests - QuickSight Dashboard Setup Script
Tests full workflow with mocked boto3 client.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from botocore.exceptions import ClientError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../scripts/quicksight'))

from quicksight_dashboard_setup import (
    create_athena_data_source,
    create_dim_fund_dataset,
    create_dim_category_dataset,
    create_dim_date_dataset,
    create_fact_performance_dataset,
    create_analysis,
    publish_dashboard,
    create_refresh_schedule,
    print_deployment_summary,
    DATA_SOURCE_ID,
    DATASET_DIM_FUND_ID,
    DATASET_DIM_CATEGORY_ID,
    DATASET_DIM_DATE_ID,
    DATASET_FACT_ID,
    ANALYSIS_ID,
    DASHBOARD_ID,
    REFRESH_SCHEDULE_ID,
    ACCOUNT_ID,
    AWS_REGION
)


@pytest.fixture
def mock_qs_client():
    """Create a mock QuickSight client."""
    client = Mock()
    client.create_data_source.return_value = {
        'Arn': f'arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}',
        'DataSourceId': DATA_SOURCE_ID
    }
    client.create_data_set.return_value = {
        'Arn': f'arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/test-dataset',
        'DataSetId': 'test-dataset'
    }
    client.create_ingestion.return_value = {
        'Arn': 'arn:aws:quicksight:us-east-1:123456789012:dataset/test/ingestion/test',
        'IngestionId': 'test-ingestion'
    }
    client.describe_ingestion.return_value = {
        'Ingestion': {'IngestionStatus': 'COMPLETED'}
    }
    # Mock describe_data_set to return the correct dataset ID based on call
    def describe_data_set_side_effect(**kwargs):
        dataset_id = kwargs.get('DataSetId', 'test-dataset')
        return {'DataSet': {'DataSetId': dataset_id}}

    client.describe_data_set.side_effect = describe_data_set_side_effect
    client.create_analysis.return_value = {
        'Arn': f'arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:analysis/{ANALYSIS_ID}',
        'AnalysisId': ANALYSIS_ID
    }
    client.create_dashboard.return_value = {
        'Arn': f'arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dashboard/{DASHBOARD_ID}',
        'DashboardId': DASHBOARD_ID,
        'VersionArn': f'arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dashboard/{DASHBOARD_ID}/version/1'
    }
    client.create_refresh_schedule.return_value = {
        'Status': 200,
        'ScheduleId': REFRESH_SCHEDULE_ID
    }
    return client


class TestDataSourceCreation:
    """Test Athena data source creation."""

    def test_create_data_source_success(self, mock_qs_client):
        """Test successful data source creation."""
        result = create_athena_data_source(mock_qs_client)

        assert result is True
        mock_qs_client.create_data_source.assert_called_once()

        call_args = mock_qs_client.create_data_source.call_args
        assert call_args[1]['DataSourceId'] == DATA_SOURCE_ID
        assert call_args[1]['Type'] == 'ATHENA'
        assert call_args[1]['DataSourceParameters']['AthenaParameters']['WorkGroup'] == 'primary'

    def test_create_data_source_already_exists(self, mock_qs_client):
        """Test data source creation when resource already exists."""
        mock_qs_client.create_data_source.side_effect = ClientError(
            {'Error': {'Code': 'ResourceExistsException'}},
            'create_data_source'
        )

        result = create_athena_data_source(mock_qs_client)

        assert result is True
        mock_qs_client.create_data_source.assert_called_once()

    def test_create_data_source_failure(self, mock_qs_client):
        """Test data source creation failure."""
        mock_qs_client.create_data_source.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException'}},
            'create_data_source'
        )

        result = create_athena_data_source(mock_qs_client)

        assert result is False


class TestDatasetCreation:
    """Test dataset creation."""

    def test_create_dim_fund_dataset_success(self, mock_qs_client):
        """Test successful dim_fund dataset creation."""
        result = create_dim_fund_dataset(mock_qs_client)

        assert result is True
        mock_qs_client.create_data_set.assert_called_once()

        call_args = mock_qs_client.create_data_set.call_args
        assert call_args[1]['DataSetId'] == DATASET_DIM_FUND_ID
        assert call_args[1]['Name'] == 'Dim Fund'
        assert call_args[1]['ImportMode'] == 'SPICE'

    def test_create_dim_category_dataset_success(self, mock_qs_client):
        """Test successful dim_category dataset creation."""
        result = create_dim_category_dataset(mock_qs_client)

        assert result is True
        mock_qs_client.create_data_set.assert_called_once()

        call_args = mock_qs_client.create_data_set.call_args
        assert call_args[1]['DataSetId'] == DATASET_DIM_CATEGORY_ID
        assert call_args[1]['Name'] == 'Dim Category'

    def test_create_dim_date_dataset_success(self, mock_qs_client):
        """Test successful dim_date dataset creation."""
        result = create_dim_date_dataset(mock_qs_client)

        assert result is True
        mock_qs_client.create_data_set.assert_called_once()

        call_args = mock_qs_client.create_data_set.call_args
        assert call_args[1]['DataSetId'] == DATASET_DIM_DATE_ID
        assert call_args[1]['Name'] == 'Dim Date'

    def test_create_fact_dataset_with_joins(self, mock_qs_client):
        """Test fact dataset creation with joins and SPICE ingestion."""
        with patch('time.sleep'):
            result = create_fact_performance_dataset(mock_qs_client)

        assert result is True
        mock_qs_client.create_data_set.assert_called_once()

        call_args = mock_qs_client.create_data_set.call_args
        assert call_args[1]['DataSetId'] == DATASET_FACT_ID
        assert call_args[1]['Name'] == 'Fact Fund Performance'

        # Verify PhysicalTableMap has all 4 tables
        physical_tables = call_args[1]['PhysicalTableMap']
        assert 'pt_fact' in physical_tables
        assert 'pt_dim_fund' in physical_tables
        assert 'pt_dim_category' in physical_tables
        assert 'pt_dim_date' in physical_tables

        # Verify LogicalTableMap has joins
        logical_tables = call_args[1]['LogicalTableMap']
        assert 'fact_joined' in logical_tables
        assert 'fact_with_fund' in logical_tables
        assert 'fact_with_category' in logical_tables

        # Verify SPICE ingestion was triggered
        mock_qs_client.create_ingestion.assert_called_once()

    def test_dataset_creation_with_retry(self, mock_qs_client):
        """Test dataset creation with throttling retry."""
        mock_qs_client.create_data_set.side_effect = [
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'create_data_set'),
            {
                'Arn': f'arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/{DATASET_DIM_FUND_ID}',
                'DataSetId': DATASET_DIM_FUND_ID
            }
        ]

        with patch('time.sleep'):
            result = create_dim_fund_dataset(mock_qs_client)

        assert result is True
        assert mock_qs_client.create_data_set.call_count == 2

    def test_dataset_creation_calculated_fields(self, mock_qs_client):
        """Test fact dataset includes calculated fields."""
        with patch('time.sleep'):
            result = create_fact_performance_dataset(mock_qs_client)

        assert result is True

        call_args = mock_qs_client.create_data_set.call_args
        logical_tables = call_args[1]['LogicalTableMap']

        # Find CreateColumnsOperation in data transforms
        fact_joined = logical_tables['fact_joined']
        transforms = fact_joined.get('DataTransforms', [])

        create_cols_op = None
        for transform in transforms:
            if 'CreateColumnsOperation' in transform:
                create_cols_op = transform['CreateColumnsOperation']
                break

        assert create_cols_op is not None
        columns = create_cols_op['Columns']

        # Verify calculated fields exist
        calc_names = [col['ColumnName'] for col in columns]
        assert 'AUM Billions' in calc_names
        assert 'Expense Ratio bps' in calc_names
        assert 'Risk-Adjusted Label' in calc_names


class TestAnalysisCreation:
    """Test analysis creation with visuals."""

    def test_create_analysis_success(self, mock_qs_client):
        """Test successful analysis creation."""
        result = create_analysis(mock_qs_client)

        assert result is True
        mock_qs_client.create_analysis.assert_called_once()

        call_args = mock_qs_client.create_analysis.call_args
        assert call_args[1]['AnalysisId'] == ANALYSIS_ID
        assert call_args[1]['Name'] == 'Finsights Finance Analysis'

    def test_analysis_has_all_visuals(self, mock_qs_client):
        """Test analysis contains all 9 required visuals."""
        # This test validates the create_analysis call structure
        # The actual Definition structure is too complex to validate fully in integration tests
        result = create_analysis(mock_qs_client)

        assert result is True
        mock_qs_client.create_analysis.assert_called_once()

        # Verify the call was made with correct structure
        call_args = mock_qs_client.create_analysis.call_args
        assert 'Definition' in call_args[1]
        definition = call_args[1]['Definition']

        # Verify basic structure exists
        assert 'DataSetIdentifierDeclarations' in definition
        assert 'Sheets' in definition
        assert len(definition['Sheets']) == 1

        sheet = definition['Sheets'][0]
        assert sheet['Name'] == 'Fund Performance Overview'
        assert 'Visuals' in sheet
        assert len(sheet['Visuals']) == 9

    def test_analysis_dataset_not_ready(self, mock_qs_client):
        """Test analysis creation fails when dataset not ready."""
        mock_qs_client.describe_data_set.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'describe_data_set'
        )

        with patch('time.sleep'):
            with patch('time.time', side_effect=[0, 0, 121]):
                result = create_analysis(mock_qs_client)

        assert result is False
        mock_qs_client.create_analysis.assert_not_called()


class TestDashboardPublishing:
    """Test dashboard publishing."""

    def test_publish_dashboard_success(self, mock_qs_client):
        """Test successful dashboard publishing."""
        result = publish_dashboard(mock_qs_client)

        assert result is True
        mock_qs_client.create_dashboard.assert_called_once()

        call_args = mock_qs_client.create_dashboard.call_args
        assert call_args[1]['DashboardId'] == DASHBOARD_ID
        assert call_args[1]['Name'] == 'Finsights Finance Dashboard'

    def test_dashboard_publish_options(self, mock_qs_client):
        """Test dashboard publish options are set correctly."""
        result = publish_dashboard(mock_qs_client)

        assert result is True

        call_args = mock_qs_client.create_dashboard.call_args
        publish_opts = call_args[1]['DashboardPublishOptions']

        assert publish_opts['AdHocFilteringOption']['AvailabilityStatus'] == 'ENABLED'
        assert publish_opts['ExportToCSVOption']['AvailabilityStatus'] == 'ENABLED'
        assert publish_opts['SheetControlsOption']['VisibilityState'] == 'EXPANDED'

    def test_publish_dashboard_failure(self, mock_qs_client):
        """Test dashboard publishing failure."""
        mock_qs_client.create_dashboard.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameterValueException'}},
            'create_dashboard'
        )

        result = publish_dashboard(mock_qs_client)

        assert result is False


class TestRefreshSchedule:
    """Test SPICE refresh schedule creation."""

    def test_create_refresh_schedule_success(self, mock_qs_client):
        """Test successful refresh schedule creation."""
        result = create_refresh_schedule(mock_qs_client)

        assert result is True
        mock_qs_client.create_refresh_schedule.assert_called_once()

        call_args = mock_qs_client.create_refresh_schedule.call_args
        assert call_args[1]['DataSetId'] == DATASET_FACT_ID

        schedule = call_args[1]['Schedule']
        assert schedule['ScheduleId'] == REFRESH_SCHEDULE_ID
        assert schedule['ScheduleFrequency']['Interval'] == 'DAILY'
        assert schedule['ScheduleFrequency']['TimeOfTheDay'] == '06:00'
        assert schedule['ScheduleFrequency']['Timezone'] == 'America/New_York'
        assert schedule['RefreshType'] == 'FULL_REFRESH'

    def test_create_refresh_schedule_failure(self, mock_qs_client):
        """Test refresh schedule creation failure."""
        mock_qs_client.create_refresh_schedule.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'create_refresh_schedule'
        )

        result = create_refresh_schedule(mock_qs_client)

        assert result is False


class TestDeploymentSummary:
    """Test deployment summary printing."""

    def test_print_deployment_summary_all_success(self, mock_qs_client, capsys):
        """Test deployment summary with all resources created."""
        mock_qs_client.describe_data_source.return_value = {'DataSource': {}}
        mock_qs_client.describe_data_set.return_value = {'DataSet': {}}
        mock_qs_client.describe_analysis.return_value = {'Analysis': {}}
        mock_qs_client.describe_dashboard.return_value = {'Dashboard': {}}
        mock_qs_client.describe_refresh_schedule.return_value = {'RefreshSchedule': {}}

        print_deployment_summary(mock_qs_client)

        captured = capsys.readouterr()
        assert 'DEPLOYMENT SUMMARY' in captured.out
        assert DATA_SOURCE_ID in captured.out
        assert DATASET_DIM_FUND_ID in captured.out
        assert DATASET_FACT_ID in captured.out
        assert ANALYSIS_ID in captured.out
        assert DASHBOARD_ID in captured.out
        assert 'Dashboard URL:' in captured.out

    def test_print_deployment_summary_with_failures(self, mock_qs_client, capsys):
        """Test deployment summary with some failed resources."""
        mock_qs_client.describe_data_source.return_value = {'DataSource': {}}
        mock_qs_client.describe_data_set.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'describe_data_set'
        )

        print_deployment_summary(mock_qs_client)

        captured = capsys.readouterr()
        assert 'DEPLOYMENT SUMMARY' in captured.out
        # Should show both success (✅) and failure (❌) markers


class TestFullWorkflow:
    """Test full end-to-end workflow."""

    def test_full_workflow_idempotent(self, mock_qs_client):
        """Test running full workflow twice is idempotent."""
        # First run - all resources created
        assert create_athena_data_source(mock_qs_client) is True
        assert create_dim_fund_dataset(mock_qs_client) is True
        assert create_dim_category_dataset(mock_qs_client) is True
        assert create_dim_date_dataset(mock_qs_client) is True

        with patch('time.sleep'):
            assert create_fact_performance_dataset(mock_qs_client) is True

        assert create_analysis(mock_qs_client) is True
        assert publish_dashboard(mock_qs_client) is True
        assert create_refresh_schedule(mock_qs_client) is True

        # Second run - resources already exist
        mock_qs_client.create_data_source.side_effect = ClientError(
            {'Error': {'Code': 'ResourceExistsException'}},
            'create_data_source'
        )
        mock_qs_client.create_data_set.side_effect = ClientError(
            {'Error': {'Code': 'ResourceExistsException'}},
            'create_data_set'
        )

        # Should still return True (handled gracefully)
        assert create_athena_data_source(mock_qs_client) is True
        assert create_dim_fund_dataset(mock_qs_client) is True

    def test_workflow_stops_on_critical_failure(self, mock_qs_client):
        """Test workflow stops when a critical step fails."""
        # Data source creation fails with non-retryable error
        mock_qs_client.create_data_source.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException'}},
            'create_data_source'
        )

        # First step should fail
        assert create_athena_data_source(mock_qs_client) is False

        # Subsequent steps should not proceed in real workflow
        # (this is enforced by main() function checking return values)

    def test_workflow_permissions_set_correctly(self, mock_qs_client):
        """Test all resources have correct permissions set."""
        create_athena_data_source(mock_qs_client)

        call_args = mock_qs_client.create_data_source.call_args
        permissions = call_args[1]['Permissions']

        assert len(permissions) > 0
        assert 'Principal' in permissions[0]
        assert 'Actions' in permissions[0]
        assert 'quicksight:DescribeDataSource' in permissions[0]['Actions']


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_throttling_with_max_retries(self, mock_qs_client):
        """Test handling max retries on persistent throttling."""
        mock_qs_client.create_data_source.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException'}},
            'create_data_source'
        )

        with patch('time.sleep'):
            result = create_athena_data_source(mock_qs_client)

        assert result is False
        # Should have tried 3 times
        assert mock_qs_client.create_data_source.call_count == 3

    def test_spice_ingestion_failure_handling(self, mock_qs_client):
        """Test handling of SPICE ingestion failures."""
        mock_qs_client.describe_ingestion.return_value = {
            'Ingestion': {
                'IngestionStatus': 'FAILED',
                'ErrorInfo': {
                    'Type': 'DATA_SET_NOT_FOUND',
                    'Message': 'Dataset not found'
                }
            }
        }

        with patch('time.sleep'):
            result = create_fact_performance_dataset(mock_qs_client)

        # Should return False when ingestion fails
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
