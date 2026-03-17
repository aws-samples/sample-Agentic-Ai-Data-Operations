"""
Unit Tests - QuickSight Dashboard Setup Script
Tests utility functions, formatting, error handling, and retry logic.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Import functions from the QuickSight script
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../scripts/quicksight'))

from quicksight_dashboard_setup import (
    retry_with_backoff,
    format_column_rename,
    poll_spice_ingestion,
    wait_for_dataset_creation
)


class TestRetryWithBackoff:
    """Test retry_with_backoff function."""

    def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt."""
        mock_func = Mock(return_value="success")
        result = retry_with_backoff(mock_func, max_retries=3, base_delay=0.1)

        assert result == "success"
        assert mock_func.call_count == 1

    def test_success_after_throttling(self):
        """Test function succeeds after throttling exceptions."""
        mock_func = Mock()
        mock_func.side_effect = [
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'test_operation'),
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'test_operation'),
            "success"
        ]

        result = retry_with_backoff(mock_func, max_retries=3, base_delay=0.1)

        assert result == "success"
        assert mock_func.call_count == 3

    def test_resource_exists_returns_none(self):
        """Test ResourceExistsException returns None without retrying."""
        mock_func = Mock()
        mock_func.side_effect = ClientError(
            {'Error': {'Code': 'ResourceExistsException'}},
            'test_operation'
        )

        result = retry_with_backoff(mock_func, max_retries=3, base_delay=0.1)

        assert result is None
        assert mock_func.call_count == 1

    def test_max_retries_exceeded(self):
        """Test exception raised when max retries exceeded."""
        mock_func = Mock()
        mock_func.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException'}},
            'test_operation'
        )

        with pytest.raises(ClientError):
            retry_with_backoff(mock_func, max_retries=3, base_delay=0.1)

        assert mock_func.call_count == 3

    def test_non_throttling_error_raises_immediately(self):
        """Test non-throttling errors are raised immediately."""
        mock_func = Mock()
        mock_func.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameterValueException'}},
            'test_operation'
        )

        with pytest.raises(ClientError):
            retry_with_backoff(mock_func, max_retries=3, base_delay=0.1)

        assert mock_func.call_count == 1

    def test_exponential_backoff_timing(self):
        """Test exponential backoff delays."""
        mock_func = Mock()
        mock_func.side_effect = [
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'test_operation'),
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'test_operation'),
            "success"
        ]

        start = time.time()
        result = retry_with_backoff(mock_func, max_retries=3, base_delay=0.1)
        elapsed = time.time() - start

        # Should have delays of 0.1s and 0.2s (total ~0.3s)
        assert elapsed >= 0.3
        assert elapsed < 0.5
        assert result == "success"


class TestFormatColumnRename:
    """Test format_column_rename function."""

    def test_simple_snake_case(self):
        """Test simple snake_case conversion."""
        assert format_column_rename("fund_ticker") == "Fund Ticker"
        assert format_column_rename("fund_name") == "Fund Name"
        assert format_column_rename("asset_class") == "Asset Class"

    def test_percentage_conversion(self):
        """Test percentage (pct) conversion."""
        assert format_column_rename("expense_ratio_pct") == "Expense Ratio %"
        assert format_column_rename("dividend_yield_pct") == "Dividend Yield %"
        assert format_column_rename("return_1yr_pct") == "Return 1Y %"

    def test_time_period_conversion(self):
        """Test time period abbreviations."""
        assert format_column_rename("return_1mo_pct") == "Return 1M %"
        assert format_column_rename("return_3mo_pct") == "Return 3M %"
        assert format_column_rename("return_ytd_pct") == "Return YTD %"
        assert format_column_rename("return_1yr_pct") == "Return 1Y %"
        assert format_column_rename("return_3yr_pct") == "Return 3Y %"
        assert format_column_rename("return_5yr_pct") == "Return 5Y %"

    def test_acronym_conversion(self):
        """Test acronym conversions (NAV, AUM)."""
        assert format_column_rename("nav") == "NAV"
        assert format_column_rename("total_assets_millions") == "Total Assets Millions"

    def test_multi_word_columns(self):
        """Test multi-word column names."""
        assert format_column_rename("management_company") == "Management Company"
        assert format_column_rename("morningstar_rating") == "Morningstar Rating"
        assert format_column_rename("geographic_focus") == "Geographic Focus"

    def test_numeric_columns(self):
        """Test columns with numbers."""
        assert format_column_rename("return_1yr_pct") == "Return 1Y %"
        assert format_column_rename("return_3yr_pct") == "Return 3Y %"
        assert format_column_rename("return_5yr_pct") == "Return 5Y %"

    def test_edge_cases(self):
        """Test edge cases."""
        assert format_column_rename("id") == "Id"
        assert format_column_rename("key") == "Key"
        assert format_column_rename("date_key") == "Date Key"


class TestPollSpiceIngestion:
    """Test poll_spice_ingestion function."""

    def test_completed_immediately(self):
        """Test ingestion completed on first check."""
        mock_client = Mock()
        mock_client.describe_ingestion.return_value = {
            'Ingestion': {
                'IngestionStatus': 'COMPLETED'
            }
        }

        result = poll_spice_ingestion(mock_client, "test-dataset", "test-ingestion", timeout=10)

        assert result is True
        assert mock_client.describe_ingestion.call_count == 1

    def test_completed_after_running(self):
        """Test ingestion completes after running status."""
        mock_client = Mock()
        mock_client.describe_ingestion.side_effect = [
            {'Ingestion': {'IngestionStatus': 'INITIALIZED'}},
            {'Ingestion': {'IngestionStatus': 'RUNNING'}},
            {'Ingestion': {'IngestionStatus': 'COMPLETED'}}
        ]

        with patch('time.sleep'):  # Mock sleep to speed up test
            result = poll_spice_ingestion(mock_client, "test-dataset", "test-ingestion", timeout=60)

        assert result is True
        assert mock_client.describe_ingestion.call_count == 3

    def test_failed_ingestion(self):
        """Test failed ingestion status."""
        mock_client = Mock()
        mock_client.describe_ingestion.return_value = {
            'Ingestion': {
                'IngestionStatus': 'FAILED',
                'ErrorInfo': {'Type': 'DATA_SET_NOT_FOUND', 'Message': 'Dataset not found'}
            }
        }

        result = poll_spice_ingestion(mock_client, "test-dataset", "test-ingestion", timeout=10)

        assert result is False

    def test_timeout(self):
        """Test timeout when ingestion takes too long."""
        mock_client = Mock()
        mock_client.describe_ingestion.return_value = {
            'Ingestion': {'IngestionStatus': 'RUNNING'}
        }

        with patch('time.sleep'):
            with patch('time.time', side_effect=[0, 0, 601]):  # Simulate timeout
                result = poll_spice_ingestion(mock_client, "test-dataset", "test-ingestion", timeout=600)

        assert result is False

    def test_client_error_handling(self):
        """Test handling of client errors during polling."""
        mock_client = Mock()
        mock_client.describe_ingestion.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'describe_ingestion'
        )

        result = poll_spice_ingestion(mock_client, "test-dataset", "test-ingestion", timeout=10)

        assert result is False


class TestWaitForDatasetCreation:
    """Test wait_for_dataset_creation function."""

    def test_dataset_ready_immediately(self):
        """Test dataset is ready on first check."""
        mock_client = Mock()
        mock_client.describe_data_set.return_value = {
            'DataSet': {'DataSetId': 'test-dataset'}
        }

        result = wait_for_dataset_creation(mock_client, "test-dataset", timeout=10)

        assert result is True
        assert mock_client.describe_data_set.call_count == 1

    def test_dataset_ready_after_wait(self):
        """Test dataset becomes ready after waiting."""
        mock_client = Mock()
        mock_client.describe_data_set.side_effect = [
            ClientError({'Error': {'Code': 'ResourceNotFoundException'}}, 'describe_data_set'),
            ClientError({'Error': {'Code': 'ResourceNotFoundException'}}, 'describe_data_set'),
            {'DataSet': {'DataSetId': 'test-dataset'}}
        ]

        with patch('time.sleep'):
            result = wait_for_dataset_creation(mock_client, "test-dataset", timeout=60)

        assert result is True
        assert mock_client.describe_data_set.call_count == 3

    def test_timeout_waiting_for_dataset(self):
        """Test timeout when dataset never becomes ready."""
        mock_client = Mock()
        mock_client.describe_data_set.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'describe_data_set'
        )

        with patch('time.sleep'):
            with patch('time.time', side_effect=[0, 0, 121]):  # Simulate timeout
                result = wait_for_dataset_creation(mock_client, "test-dataset", timeout=120)

        assert result is False

    def test_unexpected_error_raises(self):
        """Test unexpected errors are raised."""
        mock_client = Mock()
        mock_client.describe_data_set.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException'}},
            'describe_data_set'
        )

        with pytest.raises(ClientError):
            wait_for_dataset_creation(mock_client, "test-dataset", timeout=10)


class TestResourceIDFormatting:
    """Test resource ID formatting conventions."""

    def test_data_source_id_format(self):
        """Test data source ID follows naming convention."""
        from quicksight_dashboard_setup import DATA_SOURCE_ID

        assert DATA_SOURCE_ID.islower()
        assert '-' in DATA_SOURCE_ID
        assert DATA_SOURCE_ID == "finsights-athena-source"

    def test_dataset_id_format(self):
        """Test dataset IDs follow naming convention."""
        from quicksight_dashboard_setup import (
            DATASET_DIM_FUND_ID,
            DATASET_DIM_CATEGORY_ID,
            DATASET_DIM_DATE_ID,
            DATASET_FACT_ID
        )

        for dataset_id in [DATASET_DIM_FUND_ID, DATASET_DIM_CATEGORY_ID,
                           DATASET_DIM_DATE_ID, DATASET_FACT_ID]:
            assert dataset_id.islower()
            assert '-' in dataset_id
            assert dataset_id.startswith('finsights-')

    def test_analysis_dashboard_id_format(self):
        """Test analysis and dashboard IDs follow naming convention."""
        from quicksight_dashboard_setup import ANALYSIS_ID, DASHBOARD_ID

        assert ANALYSIS_ID.islower()
        assert DASHBOARD_ID.islower()
        assert '-' in ANALYSIS_ID
        assert '-' in DASHBOARD_ID


class TestConfigurationConstants:
    """Test configuration constants are properly set."""

    def test_aws_region(self):
        """Test AWS region is set."""
        from quicksight_dashboard_setup import AWS_REGION

        assert AWS_REGION == "us-east-1"

    def test_glue_database(self):
        """Test Glue database name."""
        from quicksight_dashboard_setup import GLUE_DATABASE

        assert GLUE_DATABASE == "finsights_gold"

    def test_athena_workgroup(self):
        """Test Athena workgroup."""
        from quicksight_dashboard_setup import ATHENA_WORKGROUP

        assert ATHENA_WORKGROUP == "primary"

    def test_refresh_schedule_id(self):
        """Test refresh schedule ID."""
        from quicksight_dashboard_setup import REFRESH_SCHEDULE_ID

        assert REFRESH_SCHEDULE_ID == "daily-refresh-001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
