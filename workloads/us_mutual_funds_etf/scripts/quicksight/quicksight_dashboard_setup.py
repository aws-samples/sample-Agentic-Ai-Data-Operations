"""
QuickSight Dashboard Setup - US Mutual Funds & ETF
Provisions a complete QuickSight dashboard with data source, datasets, analysis, and refresh schedule.

This script creates:
1. Athena data source connected to Gold zone
2. Four datasets (dim_fund, dim_category, dim_date, fact_fund_performance with joins)
3. Analysis with 9 visuals (KPIs, bar chart, line chart, donut, scatter, pivot table)
4. Published dashboard with permissions
5. Daily SPICE refresh schedule

Usage:
    python3 quicksight_dashboard_setup.py

Environment Variables Required:
    AWS_ACCOUNT_ID - AWS account ID (12 digits)
    QS_AUTHOR_ARN - QuickSight user/group ARN with author permissions
    AWS_REGION - AWS region (default: us-east-1)
"""

import boto3
import time
import sys
from typing import Dict, Any, List, Tuple
from botocore.exceptions import ClientError

# ============================================================================
# CONFIGURATION
# ============================================================================

AWS_REGION = "us-east-1"
ACCOUNT_ID = "123456789012"
QS_AUTHOR_ARN = "arn:aws:quicksight:us-east-1:123456789012:user/default/demo-role/demo-user"

# Resource IDs (must be lowercase, hyphen-separated)
DATA_SOURCE_ID = "finsights-athena-source"
DATASET_DIM_FUND_ID = "finsights-dim-fund"
DATASET_DIM_CATEGORY_ID = "finsights-dim-category"
DATASET_DIM_DATE_ID = "finsights-dim-date"
DATASET_FACT_ID = "finsights-fact-performance"
ANALYSIS_ID = "finsights-finance-analysis"
DASHBOARD_ID = "finsights-finance-dashboard"
REFRESH_SCHEDULE_ID = "daily-refresh-001"

# Glue catalog configuration
GLUE_DATABASE = "finsights_gold"
ATHENA_WORKGROUP = "primary"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def retry_with_backoff(func, max_retries=3, base_delay=2):
    """
    Retry a function with exponential backoff on throttling errors.

    Args:
        func: Function to execute (no arguments)
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (exponentially increased)

    Returns:
        Function result if successful

    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func()
        except ClientError as e:
            error_code = e.response['Error']['Code']
            last_exception = e
            if error_code == 'ThrottlingException' and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"  ⚠️  Throttled, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            elif error_code == 'ResourceExistsException':
                print(f"  ℹ️  Resource already exists, skipping")
                return None
            elif error_code != 'ThrottlingException':
                # Non-throttling errors should raise immediately
                raise
    # If we get here, we exhausted retries on ThrottlingException
    raise last_exception


def format_column_rename(column_name: str) -> str:
    """
    Convert snake_case column names to human-readable labels.

    Examples:
        fund_ticker -> Fund Ticker
        return_1yr_pct -> Return 1Y %
        total_assets_millions -> Total Assets Millions
    """
    # Special cases
    replacements = {
        'pct': '%',
        '1mo': '1M',
        '3mo': '3M',
        'ytd': 'YTD',
        '1yr': '1Y',
        '3yr': '3Y',
        '5yr': '5Y',
        'nav': 'NAV',
        'aum': 'AUM'
    }

    words = column_name.split('_')
    formatted = []

    for word in words:
        if word.lower() in replacements:
            formatted.append(replacements[word.lower()])
        else:
            formatted.append(word.capitalize())

    return ' '.join(formatted)


def poll_spice_ingestion(qs_client, dataset_id: str, ingestion_id: str, timeout: int = 600) -> bool:
    """
    Poll SPICE ingestion status until complete or failed.

    Args:
        qs_client: boto3 QuickSight client
        dataset_id: Dataset ID
        ingestion_id: Ingestion ID to poll
        timeout: Maximum wait time in seconds

    Returns:
        True if successful, False if failed or timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = qs_client.describe_ingestion(
                AwsAccountId=ACCOUNT_ID,
                DataSetId=dataset_id,
                IngestionId=ingestion_id
            )

            status = response['Ingestion']['IngestionStatus']

            if status == 'COMPLETED':
                print(f"  ✅ SPICE ingestion completed")
                return True
            elif status == 'FAILED':
                print(f"  ❌ SPICE ingestion failed: {response['Ingestion'].get('ErrorInfo', 'Unknown error')}")
                return False
            elif status in ['INITIALIZED', 'QUEUED', 'RUNNING']:
                print(f"  ⏳ SPICE ingestion in progress ({status})...")
                time.sleep(10)
            else:
                print(f"  ⚠️  Unknown status: {status}")
                time.sleep(10)

        except ClientError as e:
            print(f"  ❌ Error polling ingestion: {e}")
            return False

    print(f"  ⏱️  Timeout waiting for SPICE ingestion")
    return False


def wait_for_dataset_creation(qs_client, dataset_id: str, timeout: int = 120) -> bool:
    """
    Wait for dataset to be fully created before proceeding.

    Args:
        qs_client: boto3 QuickSight client
        dataset_id: Dataset ID to check
        timeout: Maximum wait time in seconds

    Returns:
        True if dataset is ready, False otherwise
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = qs_client.describe_data_set(
                AwsAccountId=ACCOUNT_ID,
                DataSetId=dataset_id
            )

            if response['DataSet']['DataSetId'] == dataset_id:
                print(f"  ✅ Dataset {dataset_id} is ready")
                return True

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                print(f"  ⏳ Waiting for dataset {dataset_id} to be created...")
                time.sleep(5)
            else:
                raise

    print(f"  ⏱️  Timeout waiting for dataset {dataset_id}")
    return False


# ============================================================================
# STEP 1: CREATE ATHENA DATA SOURCE
# ============================================================================

def create_athena_data_source(qs_client) -> bool:
    """Create Athena data source for Gold zone access."""
    print("\n[STEP 1] Creating Athena Data Source...")

    def _create():
        return qs_client.create_data_source(
            AwsAccountId=ACCOUNT_ID,
            DataSourceId=DATA_SOURCE_ID,
            Name="Finsights Athena - Gold Zone",
            Type="ATHENA",
            DataSourceParameters={
                'AthenaParameters': {
                    'WorkGroup': ATHENA_WORKGROUP
                }
            },
            Permissions=[
                {
                    'Principal': QS_AUTHOR_ARN,
                    'Actions': [
                        'quicksight:DescribeDataSource',
                        'quicksight:DescribeDataSourcePermissions',
                        'quicksight:PassDataSource',
                        'quicksight:UpdateDataSource',
                        'quicksight:DeleteDataSource',
                        'quicksight:UpdateDataSourcePermissions'
                    ]
                }
            ],
            SslProperties={
                'DisableSsl': False
            }
        )

    try:
        response = retry_with_backoff(_create)
        if response:
            print(f"  ✅ Data source created: {DATA_SOURCE_ID}")
            print(f"     ARN: {response['Arn']}")
        return True
    except ClientError as e:
        print(f"  ❌ Failed to create data source: {e}")
        return False


# ============================================================================
# STEP 2: CREATE DATASETS
# ============================================================================

def create_dim_fund_dataset(qs_client) -> bool:
    """Create dim_fund dataset."""
    print("\n[STEP 2A] Creating Dataset: dim_fund...")

    columns = [
        'fund_ticker', 'fund_name', 'fund_type', 'management_company',
        'inception_date', 'fund_category', 'geographic_focus', 'sector_focus',
        'asset_class', 'benchmark_index', 'morningstar_category'
    ]

    def _create():
        return qs_client.create_data_set(
            AwsAccountId=ACCOUNT_ID,
            DataSetId=DATASET_DIM_FUND_ID,
            Name="Dim Fund",
            PhysicalTableMap={
                'dim-fund-physical': {
                    'RelationalTable': {
                        'DataSourceArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}",
                        'Catalog': 'AwsDataCatalog',
                        'Schema': GLUE_DATABASE,
                        'Name': 'dim_fund',
                        'InputColumns': [
                            {'Name': col, 'Type': 'STRING' if col != 'inception_date' else 'DATETIME'}
                            for col in columns
                        ]
                    }
                }
            },
            LogicalTableMap={
                'dim-fund-logical': {
                    'Alias': 'dim_fund',
                    'Source': {
                        'PhysicalTableId': 'dim-fund-physical'
                    },
                    'DataTransforms': [
                        {
                            'RenameColumnOperation': {
                                'ColumnName': col,
                                'NewColumnName': format_column_rename(col)
                            }
                        }
                        for col in columns
                    ]
                }
            },
            ImportMode='SPICE',
            Permissions=[
                {
                    'Principal': QS_AUTHOR_ARN,
                    'Actions': [
                        'quicksight:DescribeDataSet',
                        'quicksight:DescribeDataSetPermissions',
                        'quicksight:PassDataSet',
                        'quicksight:DescribeIngestion',
                        'quicksight:ListIngestions',
                        'quicksight:UpdateDataSet',
                        'quicksight:DeleteDataSet',
                        'quicksight:CreateIngestion',
                        'quicksight:CancelIngestion',
                        'quicksight:UpdateDataSetPermissions'
                    ]
                }
            ]
        )

    try:
        response = retry_with_backoff(_create)
        if response:
            print(f"  ✅ Dataset created: {DATASET_DIM_FUND_ID}")
        return True
    except ClientError as e:
        print(f"  ❌ Failed to create dataset: {e}")
        return False


def create_dim_category_dataset(qs_client) -> bool:
    """Create dim_category dataset."""
    print("\n[STEP 2B] Creating Dataset: dim_category...")

    columns = [
        'category_key', 'fund_category', 'asset_class', 'morningstar_category',
        'benchmark_index', 'geographic_focus', 'typical_expense_min', 'typical_expense_max'
    ]

    def _create():
        return qs_client.create_data_set(
            AwsAccountId=ACCOUNT_ID,
            DataSetId=DATASET_DIM_CATEGORY_ID,
            Name="Dim Category",
            PhysicalTableMap={
                'dim-category-physical': {
                    'RelationalTable': {
                        'DataSourceArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}",
                        'Catalog': 'AwsDataCatalog',
                        'Schema': GLUE_DATABASE,
                        'Name': 'dim_category',
                        'InputColumns': [
                            {
                                'Name': col,
                                'Type': 'INTEGER' if col == 'category_key' else 'DECIMAL' if 'expense' in col else 'STRING'
                            }
                            for col in columns
                        ]
                    }
                }
            },
            LogicalTableMap={
                'dim-category-logical': {
                    'Alias': 'dim_category',
                    'Source': {
                        'PhysicalTableId': 'dim-category-physical'
                    },
                    'DataTransforms': [
                        {
                            'RenameColumnOperation': {
                                'ColumnName': col,
                                'NewColumnName': format_column_rename(col)
                            }
                        }
                        for col in columns
                    ]
                }
            },
            ImportMode='SPICE',
            Permissions=[
                {
                    'Principal': QS_AUTHOR_ARN,
                    'Actions': [
                        'quicksight:DescribeDataSet',
                        'quicksight:DescribeDataSetPermissions',
                        'quicksight:PassDataSet',
                        'quicksight:DescribeIngestion',
                        'quicksight:ListIngestions',
                        'quicksight:UpdateDataSet',
                        'quicksight:DeleteDataSet',
                        'quicksight:CreateIngestion',
                        'quicksight:CancelIngestion',
                        'quicksight:UpdateDataSetPermissions'
                    ]
                }
            ]
        )

    try:
        response = retry_with_backoff(_create)
        if response:
            print(f"  ✅ Dataset created: {DATASET_DIM_CATEGORY_ID}")
        return True
    except ClientError as e:
        print(f"  ❌ Failed to create dataset: {e}")
        return False


def create_dim_date_dataset(qs_client) -> bool:
    """Create dim_date dataset."""
    print("\n[STEP 2C] Creating Dataset: dim_date...")

    columns = ['date_key', 'as_of_date', 'month', 'month_name', 'quarter', 'year']

    def _create():
        return qs_client.create_data_set(
            AwsAccountId=ACCOUNT_ID,
            DataSetId=DATASET_DIM_DATE_ID,
            Name="Dim Date",
            PhysicalTableMap={
                'dim-date-physical': {
                    'RelationalTable': {
                        'DataSourceArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}",
                        'Catalog': 'AwsDataCatalog',
                        'Schema': GLUE_DATABASE,
                        'Name': 'dim_date',
                        'InputColumns': [
                            {
                                'Name': col,
                                'Type': 'INTEGER' if col in ['date_key', 'month', 'quarter', 'year']
                                       else 'DATETIME' if col == 'as_of_date'
                                       else 'STRING'
                            }
                            for col in columns
                        ]
                    }
                }
            },
            LogicalTableMap={
                'dim-date-logical': {
                    'Alias': 'dim_date',
                    'Source': {
                        'PhysicalTableId': 'dim-date-physical'
                    },
                    'DataTransforms': [
                        {
                            'RenameColumnOperation': {
                                'ColumnName': col,
                                'NewColumnName': format_column_rename(col)
                            }
                        }
                        for col in columns
                    ]
                }
            },
            ImportMode='SPICE',
            Permissions=[
                {
                    'Principal': QS_AUTHOR_ARN,
                    'Actions': [
                        'quicksight:DescribeDataSet',
                        'quicksight:DescribeDataSetPermissions',
                        'quicksight:PassDataSet',
                        'quicksight:DescribeIngestion',
                        'quicksight:ListIngestions',
                        'quicksight:UpdateDataSet',
                        'quicksight:DeleteDataSet',
                        'quicksight:CreateIngestion',
                        'quicksight:CancelIngestion',
                        'quicksight:UpdateDataSetPermissions'
                    ]
                }
            ]
        )

    try:
        response = retry_with_backoff(_create)
        if response:
            print(f"  ✅ Dataset created: {DATASET_DIM_DATE_ID}")
        return True
    except ClientError as e:
        print(f"  ❌ Failed to create dataset: {e}")
        return False


def create_fact_performance_dataset(qs_client) -> bool:
    """Create fact_fund_performance dataset with joins to all dimensions."""
    print("\n[STEP 2D] Creating Dataset: fact_fund_performance (with joins)...")

    fact_columns = [
        'fact_id', 'fund_ticker', 'category_key', 'date_key', 'nav', 'total_assets_millions',
        'expense_ratio_pct', 'dividend_yield_pct', 'beta', 'sharpe_ratio', 'morningstar_rating',
        'return_1mo_pct', 'return_3mo_pct', 'return_ytd_pct', 'return_1yr_pct', 'return_3yr_pct', 'return_5yr_pct'
    ]

    dim_fund_cols = ['fund_name', 'fund_type', 'management_company', 'asset_class', 'fund_category', 'geographic_focus']
    dim_category_cols = ['morningstar_category', 'benchmark_index']
    dim_date_cols = ['as_of_date', 'month', 'month_name', 'quarter', 'year']

    def _create():
        return qs_client.create_data_set(
            AwsAccountId=ACCOUNT_ID,
            DataSetId=DATASET_FACT_ID,
            Name="Fact Fund Performance",
            PhysicalTableMap={
                'pt-fact': {
                    'RelationalTable': {
                        'DataSourceArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}",
                        'Catalog': 'AwsDataCatalog',
                        'Schema': GLUE_DATABASE,
                        'Name': 'fact_fund_performance',
                        'InputColumns': [
                            {
                                'Name': col,
                                'Type': 'INTEGER' if col in ['fact_id', 'category_key', 'date_key', 'morningstar_rating'] else 'DECIMAL' if col not in ['fund_ticker'] else 'STRING'
                            }
                            for col in fact_columns
                        ]
                    }
                },
                'pt-dim-fund': {
                    'RelationalTable': {
                        'DataSourceArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}",
                        'Catalog': 'AwsDataCatalog',
                        'Schema': GLUE_DATABASE,
                        'Name': 'dim_fund',
                        'InputColumns': [
                            {'Name': 'fund_ticker', 'Type': 'STRING'},
                            {'Name': 'fund_name', 'Type': 'STRING'},
                            {'Name': 'fund_type', 'Type': 'STRING'},
                            {'Name': 'management_company', 'Type': 'STRING'},
                            {'Name': 'asset_class', 'Type': 'STRING'},
                            {'Name': 'fund_category', 'Type': 'STRING'},
                            {'Name': 'geographic_focus', 'Type': 'STRING'}
                        ]
                    }
                },
                'pt-dim-category': {
                    'RelationalTable': {
                        'DataSourceArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}",
                        'Catalog': 'AwsDataCatalog',
                        'Schema': GLUE_DATABASE,
                        'Name': 'dim_category',
                        'InputColumns': [
                            {'Name': 'category_key', 'Type': 'INTEGER'},
                            {'Name': 'morningstar_category', 'Type': 'STRING'},
                            {'Name': 'benchmark_index', 'Type': 'STRING'}
                        ]
                    }
                },
                'pt-dim-date': {
                    'RelationalTable': {
                        'DataSourceArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}",
                        'Catalog': 'AwsDataCatalog',
                        'Schema': GLUE_DATABASE,
                        'Name': 'dim_date',
                        'InputColumns': [
                            {'Name': 'date_key', 'Type': 'INTEGER'},
                            {'Name': 'as_of_date', 'Type': 'DATETIME'},
                            {'Name': 'month', 'Type': 'INTEGER'},
                            {'Name': 'month_name', 'Type': 'STRING'},
                            {'Name': 'quarter', 'Type': 'INTEGER'},
                            {'Name': 'year', 'Type': 'INTEGER'}
                        ]
                    }
                }
            },
            LogicalTableMap={
                'lt-fact': {
                    'Alias': 'fact_base',
                    'Source': {
                        'PhysicalTableId': 'pt-fact'
                    }
                },
                'lt-dim-fund': {
                    'Alias': 'dim_fund_base',
                    'Source': {
                        'PhysicalTableId': 'pt-dim-fund'
                    }
                },
                'lt-dim-category': {
                    'Alias': 'dim_category_base',
                    'Source': {
                        'PhysicalTableId': 'pt-dim-category'
                    }
                },
                'lt-dim-date': {
                    'Alias': 'dim_date_base',
                    'Source': {
                        'PhysicalTableId': 'pt-dim-date'
                    }
                },
                                'fact-joined': {
                    'Alias': 'fact_performance',
                    'Source': {
                        'JoinInstruction': {
                            'LeftOperand': 'fact-with-fund',
                            'RightOperand': 'lt-dim-date',
                            'Type': 'INNER',
                            'OnClause': 'date_key = date_key'
                        }
                    },
                    'DataTransforms': [
                        {
                            'CreateColumnsOperation': {
                                'Columns': [
                                    {
                                        'ColumnName': 'AUM Billions',
                                        'ColumnId': 'calc_aum_billions',
                                        'Expression': '{total_assets_millions} / 1000'
                                    },
                                    {
                                        'ColumnName': 'Expense Ratio bps',
                                        'ColumnId': 'calc_expense_bps',
                                        'Expression': '{expense_ratio_pct} * 100'
                                    },
                                    {
                                        'ColumnName': 'Risk-Adjusted Label',
                                        'ColumnId': 'calc_risk_label',
                                        'Expression': 'ifelse({sharpe_ratio} >= 1.5, "High", ifelse({sharpe_ratio} >= 0.5, "Medium", "Low"))'
                                    }
                                ]
                            }
                        }
                    ] + [
                        {
                            'RenameColumnOperation': {
                                'ColumnName': col,
                                'NewColumnName': format_column_rename(col)
                            }
                        }
                        for col in fact_columns + dim_fund_cols + dim_category_cols + dim_date_cols
                    ]
                },
                'fact-with-fund': {
                    'Alias': 'fact-with-fund',
                    'Source': {
                        'JoinInstruction': {
                            'LeftOperand': 'fact-with-category',
                            'RightOperand': 'lt-dim-fund',
                            'Type': 'INNER',
                            'OnClause': 'fund_ticker = fund_ticker'
                        }
                    }
                },
                'fact-with-category': {
                    'Alias': 'fact-with-category',
                    'Source': {
                        'JoinInstruction': {
                            'LeftOperand': 'lt-fact',
                            'RightOperand': 'lt-dim-category',
                            'Type': 'LEFT',
                            'OnClause': 'category_key = category_key'
                        }
                    }
                }
            },
            ImportMode='SPICE',
            Permissions=[
                {
                    'Principal': QS_AUTHOR_ARN,
                    'Actions': [
                        'quicksight:DescribeDataSet',
                        'quicksight:DescribeDataSetPermissions',
                        'quicksight:PassDataSet',
                        'quicksight:DescribeIngestion',
                        'quicksight:ListIngestions',
                        'quicksight:UpdateDataSet',
                        'quicksight:DeleteDataSet',
                        'quicksight:CreateIngestion',
                        'quicksight:CancelIngestion',
                        'quicksight:UpdateDataSetPermissions'
                    ]
                }
            ]
        )

    try:
        response = retry_with_backoff(_create)
        if response:
            print(f"  ✅ Dataset created: {DATASET_FACT_ID}")

            # Trigger initial SPICE ingestion
            print(f"\n  🔄 Triggering initial SPICE ingestion for {DATASET_FACT_ID}...")
            ingestion_id = f"initial-ingestion-{int(time.time())}"

            def _ingest():
                return qs_client.create_ingestion(
                    AwsAccountId=ACCOUNT_ID,
                    DataSetId=DATASET_FACT_ID,
                    IngestionId=ingestion_id
                )

            retry_with_backoff(_ingest)

            # Poll ingestion status
            success = poll_spice_ingestion(qs_client, DATASET_FACT_ID, ingestion_id)
            return success

        return True
    except ClientError as e:
        print(f"  ❌ Failed to create dataset: {e}")
        return False


# ============================================================================
# STEP 3: CREATE ANALYSIS WITH VISUALS
# ============================================================================

def create_analysis(qs_client) -> bool:
    """Create QuickSight analysis with 9 visuals."""
    print("\n[STEP 3] Creating Analysis with 9 Visuals...")

    # Wait for fact dataset to be fully ready
    if not wait_for_dataset_creation(qs_client, DATASET_FACT_ID):
        print("  ❌ Fact dataset not ready, cannot create analysis")
        return False

    # Visual definitions
    visuals = []

    # Visual 1: KPI - Total Funds
    visuals.append({
        'KPIVisual': {
            'VisualId': 'visual-kpi-total-funds',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'Total Funds'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'TargetValues': [],
                    'TrendGroups': [],
                    'Values': [
                        {
                            'NumericalMeasureField': {
                                'FieldId': 'total_funds',
                                'Column': {
                                    'DataSetIdentifier': DATASET_FACT_ID,
                                    'ColumnName': 'Fund Ticker'
                                },
                                'AggregationFunction': {
                                    'SimpleNumericalAggregation': 'DISTINCT_COUNT'
                                }
                            }
                        }
                    ]
                },
                'SortConfiguration': {},
                'KPIOptions': {
                    'ProgressBar': {
                        'Visibility': 'HIDDEN'
                    },
                    'TrendArrows': {
                        'Visibility': 'HIDDEN'
                    },
                    'PrimaryValueDisplayType': 'ACTUAL'
                }
            }
        }
    })

    # Visual 2: KPI - Average 1Y Return
    visuals.append({
        'KPIVisual': {
            'VisualId': 'visual-kpi-avg-1y-return',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'Avg 1Y Return'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'TargetValues': [],
                    'TrendGroups': [],
                    'Values': [
                        {
                            'NumericalMeasureField': {
                                'FieldId': 'avg_1y_return',
                                'Column': {
                                    'DataSetIdentifier': DATASET_FACT_ID,
                                    'ColumnName': 'Return 1Y %'
                                },
                                'AggregationFunction': {
                                    'SimpleNumericalAggregation': 'AVERAGE'
                                },
                                'FormatConfiguration': {
                                    'FormatConfiguration': {
                                        'NumberFormatConfiguration': {
                                            'FormatConfiguration': {
                                                'PercentageFormatConfiguration': {
                                                    'DecimalPlacesConfiguration': {
                                                        'DecimalPlaces': 2
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    ]
                },
                'SortConfiguration': {},
                'KPIOptions': {
                    'ProgressBar': {
                        'Visibility': 'HIDDEN'
                    },
                    'TrendArrows': {
                        'Visibility': 'HIDDEN'
                    },
                    'PrimaryValueDisplayType': 'ACTUAL'
                }
            }
        }
    })

    # Visual 3: KPI - Total AUM
    visuals.append({
        'KPIVisual': {
            'VisualId': 'visual-kpi-total-aum',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'Total AUM (B)'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'TargetValues': [],
                    'TrendGroups': [],
                    'Values': [
                        {
                            'NumericalMeasureField': {
                                'FieldId': 'total_aum',
                                'Column': {
                                    'DataSetIdentifier': DATASET_FACT_ID,
                                    'ColumnName': 'AUM Billions'
                                },
                                'AggregationFunction': {
                                    'SimpleNumericalAggregation': 'SUM'
                                },
                                'FormatConfiguration': {
                                    'FormatConfiguration': {
                                        'NumberFormatConfiguration': {
                                            'FormatConfiguration': {
                                                'CurrencyDisplayFormatConfiguration': {
                                                    'DecimalPlacesConfiguration': {
                                                        'DecimalPlaces': 1
                                                    },
                                                    'Symbol': '$'
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    ]
                },
                'SortConfiguration': {},
                'KPIOptions': {
                    'ProgressBar': {
                        'Visibility': 'HIDDEN'
                    },
                    'TrendArrows': {
                        'Visibility': 'HIDDEN'
                    },
                    'PrimaryValueDisplayType': 'ACTUAL'
                }
            }
        }
    })

    # Visual 4: KPI - Avg Expense Ratio
    visuals.append({
        'KPIVisual': {
            'VisualId': 'visual-kpi-avg-expense',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'Avg Expense Ratio %'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'TargetValues': [],
                    'TrendGroups': [],
                    'Values': [
                        {
                            'NumericalMeasureField': {
                                'FieldId': 'avg_expense',
                                'Column': {
                                    'DataSetIdentifier': DATASET_FACT_ID,
                                    'ColumnName': 'Expense Ratio %'
                                },
                                'AggregationFunction': {
                                    'SimpleNumericalAggregation': 'AVERAGE'
                                },
                                'FormatConfiguration': {
                                    'FormatConfiguration': {
                                        'NumberFormatConfiguration': {
                                            'FormatConfiguration': {
                                                'PercentageFormatConfiguration': {
                                                    'DecimalPlacesConfiguration': {
                                                        'DecimalPlaces': 2
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    ]
                },
                'SortConfiguration': {},
                'KPIOptions': {
                    'ProgressBar': {
                        'Visibility': 'HIDDEN'
                    },
                    'TrendArrows': {
                        'Visibility': 'HIDDEN'
                    },
                    'PrimaryValueDisplayType': 'ACTUAL'
                }
            }
        }
    })

    # Visual 5: Bar Chart - Avg Returns by Asset Class
    visuals.append({
        'BarChartVisual': {
            'VisualId': 'visual-bar-returns-by-class',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'Average Returns by Asset Class'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'BarChartAggregatedFieldWells': {
                        'Category': [
                            {
                                'CategoricalDimensionField': {
                                    'FieldId': 'asset_class',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Asset Class'
                                    }
                                }
                            }
                        ],
                        'Values': [
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_return_1y',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Return 1Y %'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            },
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_return_3y',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Return 3Y %'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            },
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_return_5y',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Return 5Y %'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            }
                        ],
                        'Colors': []
                    }
                },
                'SortConfiguration': {
                    'CategorySort': [
                        {
                            'FieldSort': {
                                'FieldId': 'avg_return_1y',
                                'Direction': 'DESC'
                            }
                        }
                    ]
                },
                'Orientation': 'HORIZONTAL',
                'BarsArrangement': 'CLUSTERED',
                'Legend': {
                    'Visibility': 'VISIBLE'
                },
                'DataLabels': {
                    'Visibility': 'HIDDEN'
                }
            }
        }
    })

    # Visual 6: Line Chart - NAV Trend Over Time
    visuals.append({
        'LineChartVisual': {
            'VisualId': 'visual-line-nav-trend',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'Average NAV Over Time by Fund Type'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'LineChartAggregatedFieldWells': {
                        'Category': [
                            {
                                'DateDimensionField': {
                                    'FieldId': 'as_of_date',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'As Of Date'
                                    },
                                    'DateGranularity': 'MONTH'
                                }
                            }
                        ],
                        'Values': [
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_nav',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'NAV'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            }
                        ],
                        'Colors': [
                            {
                                'CategoricalDimensionField': {
                                    'FieldId': 'fund_type',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Fund Type'
                                    }
                                }
                            }
                        ]
                    }
                },
                'SortConfiguration': {},
                'Type': 'LINE',
                'Legend': {
                    'Visibility': 'VISIBLE'
                },
                'DataLabels': {
                    'Visibility': 'HIDDEN'
                }
            }
        }
    })

    # Visual 7: Donut Chart - AUM by Management Company
    visuals.append({
        'PieChartVisual': {
            'VisualId': 'visual-donut-aum-by-company',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'AUM Distribution by Manager'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'PieChartAggregatedFieldWells': {
                        'Category': [
                            {
                                'CategoricalDimensionField': {
                                    'FieldId': 'management_company',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Management Company'
                                    }
                                }
                            }
                        ],
                        'Values': [
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'sum_aum',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'AUM Billions'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'SUM'
                                    }
                                }
                            }
                        ]
                    }
                },
                'SortConfiguration': {},
                'DonutOptions': {
                    'ArcOptions': {
                        'ArcThickness': 'MEDIUM'
                    }
                },
                'Legend': {
                    'Visibility': 'VISIBLE',
                    'Position': 'RIGHT'
                },
                'DataLabels': {
                    'Visibility': 'VISIBLE',
                    'CategoryLabelVisibility': 'HIDDEN',
                    'MeasureLabelVisibility': 'VISIBLE'
                }
            }
        }
    })

    # Visual 8: Scatter Plot - Risk vs Return
    visuals.append({
        'ScatterPlotVisual': {
            'VisualId': 'visual-scatter-risk-return',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'Risk vs Return (sized by AUM)'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'ScatterPlotCategoricallyAggregatedFieldWells': {
                        'XAxis': [
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_beta',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Beta'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            }
                        ],
                        'YAxis': [
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_return_1y',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Return 1Y %'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            }
                        ],
                        'Size': [
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'sum_aum',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'AUM Billions'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'SUM'
                                    }
                                }
                            }
                        ],
                        'Category': [
                            {
                                'CategoricalDimensionField': {
                                    'FieldId': 'asset_class',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Asset Class'
                                    }
                                }
                            }
                        ]
                    }
                },
                'XAxisLabelOptions': {
                    'Visibility': 'VISIBLE',
                    'CustomLabel': 'Risk (Beta)'
                },
                'YAxisLabelOptions': {
                    'Visibility': 'VISIBLE',
                    'CustomLabel': '1Y Return %'
                },
                'Legend': {
                    'Visibility': 'VISIBLE'
                },
                'DataLabels': {
                    'Visibility': 'HIDDEN'
                }
            }
        }
    })

    # Visual 9: Pivot Table - Category Performance
    visuals.append({
        'PivotTableVisual': {
            'VisualId': 'visual-pivot-category-performance',
            'Title': {
                'Visibility': 'VISIBLE',
                'FormatText': {
                    'PlainText': 'Category Performance Matrix'
                }
            },
            'Subtitle': {
                'Visibility': 'HIDDEN'
            },
            'ChartConfiguration': {
                'FieldWells': {
                    'PivotTableAggregatedFieldWells': {
                        'Rows': [
                            {
                                'CategoricalDimensionField': {
                                    'FieldId': 'fund_category',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Fund Category'
                                    }
                                }
                            }
                        ],
                        'Columns': [
                            {
                                'CategoricalDimensionField': {
                                    'FieldId': 'fund_type',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Fund Type'
                                    }
                                }
                            }
                        ],
                        'Values': [
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_return_1y',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Return 1Y %'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            },
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_sharpe',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Sharpe Ratio'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            },
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'avg_expense',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Expense Ratio %'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'AVERAGE'
                                    }
                                }
                            },
                            {
                                'NumericalMeasureField': {
                                    'FieldId': 'count_funds',
                                    'Column': {
                                        'DataSetIdentifier': DATASET_FACT_ID,
                                        'ColumnName': 'Fund Ticker'
                                    },
                                    'AggregationFunction': {
                                        'SimpleNumericalAggregation': 'DISTINCT_COUNT'
                                    }
                                }
                            }
                        ]
                    }
                },
                'SortConfiguration': {},
                'TableOptions': {
                    'RowAlternateColorOptions': {
                        'Status': 'ENABLED'
                    }
                },
                'TotalOptions': {
                    'RowSubtotalOptions': {
                        'TotalsVisibility': 'HIDDEN'
                    },
                    'ColumnSubtotalOptions': {
                        'TotalsVisibility': 'HIDDEN'
                    }
                },
                'FieldOptions': {}
            },
            'ConditionalFormatting': {
                'ConditionalFormattingOptions': [
                    {
                        'Cell': {
                            'FieldId': 'avg_return_1y',
                            'TextFormat': {
                                'BackgroundColor': {
                                    'Gradient': {
                                        'Expression': 'AVG({Return 1Y %})',
                                        'Color': {
                                            'Stops': [
                                                {
                                                    'GradientOffset': 0,
                                                    'Color': '#FF0000'
                                                },
                                                {
                                                    'GradientOffset': 100,
                                                    'Color': '#00FF00'
                                                }
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }
    })

    # Create the analysis
    def _create():
        return qs_client.create_analysis(
            AwsAccountId=ACCOUNT_ID,
            AnalysisId=ANALYSIS_ID,
            Name="Finsights Finance Analysis",
            Permissions=[
                {
                    'Principal': QS_AUTHOR_ARN,
                    'Actions': [
                        'quicksight:RestoreAnalysis',
                        'quicksight:UpdateAnalysisPermissions',
                        'quicksight:DeleteAnalysis',
                        'quicksight:DescribeAnalysisPermissions',
                        'quicksight:QueryAnalysis',
                        'quicksight:DescribeAnalysis',
                        'quicksight:UpdateAnalysis'
                    ]
                }
            ],
            SourceEntity={
                'SourceTemplate': {
                    'DataSetReferences': [
                        {
                            'DataSetPlaceholder': 'fact_performance',
                            'DataSetArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/{DATASET_FACT_ID}"
                        }
                    ],
                    'Arn': 'placeholder'  # Will use Definition instead
                }
            },
            Definition={
                'DataSetIdentifierDeclarations': [
                    {
                        'Identifier': DATASET_FACT_ID,
                        'DataSetArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/{DATASET_FACT_ID}"
                    }
                ],
                'Sheets': [
                    {
                        'SheetId': 'sheet-1',
                        'Name': 'Fund Performance Overview',
                        'Visuals': visuals,
                        'Layouts': [
                            {
                                'Configuration': {
                                    'GridLayout': {
                                        'Elements': [
                                            {'ElementId': f'visual-{i}', 'ElementType': 'VISUAL',
                                             'ColumnIndex': (i % 3) * 4, 'ColumnSpan': 4,
                                             'RowIndex': (i // 3) * 6, 'RowSpan': 6}
                                            for i in range(9)
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        )

    try:
        response = retry_with_backoff(_create)
        if response:
            print(f"  ✅ Analysis created: {ANALYSIS_ID}")
            print(f"     ARN: {response['Arn']}")
        return True
    except ClientError as e:
        print(f"  ❌ Failed to create analysis: {e}")
        # Print detailed error for debugging
        if hasattr(e, 'response') and 'Error' in e.response:
            print(f"     Error details: {e.response['Error']}")
        return False


# ============================================================================
# STEP 4: PUBLISH DASHBOARD
# ============================================================================

def publish_dashboard(qs_client) -> bool:
    """Publish dashboard from analysis."""
    print("\n[STEP 4] Publishing Dashboard...")

    def _create():
        return qs_client.create_dashboard(
            AwsAccountId=ACCOUNT_ID,
            DashboardId=DASHBOARD_ID,
            Name="Finsights Finance Dashboard",
            Permissions=[
                {
                    'Principal': QS_AUTHOR_ARN,
                    'Actions': [
                        'quicksight:DescribeDashboard',
                        'quicksight:ListDashboardVersions',
                        'quicksight:UpdateDashboardPermissions',
                        'quicksight:QueryDashboard',
                        'quicksight:UpdateDashboard',
                        'quicksight:DeleteDashboard',
                        'quicksight:DescribeDashboardPermissions',
                        'quicksight:UpdateDashboardPublishedVersion'
                    ]
                }
            ],
            SourceEntity={
                'SourceTemplate': {
                    'DataSetReferences': [
                        {
                            'DataSetPlaceholder': 'fact_performance',
                            'DataSetArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/{DATASET_FACT_ID}"
                        }
                    ],
                    'Arn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:analysis/{ANALYSIS_ID}"
                }
            },
            DashboardPublishOptions={
                'AdHocFilteringOption': {
                    'AvailabilityStatus': 'ENABLED'
                },
                'ExportToCSVOption': {
                    'AvailabilityStatus': 'ENABLED'
                },
                'SheetControlsOption': {
                    'VisibilityState': 'EXPANDED'
                }
            }
        )

    try:
        response = retry_with_backoff(_create)
        if response:
            print(f"  ✅ Dashboard published: {DASHBOARD_ID}")
            print(f"     ARN: {response['Arn']}")
            print(f"     Version: {response['VersionArn']}")
        return True
    except ClientError as e:
        print(f"  ❌ Failed to publish dashboard: {e}")
        return False


# ============================================================================
# STEP 5: CONFIGURE SPICE REFRESH SCHEDULE
# ============================================================================

def create_refresh_schedule(qs_client) -> bool:
    """Create daily SPICE refresh schedule for fact dataset."""
    print("\n[STEP 5] Creating SPICE Refresh Schedule...")

    def _create():
        return qs_client.create_refresh_schedule(
            AwsAccountId=ACCOUNT_ID,
            DataSetId=DATASET_FACT_ID,
            Schedule={
                'ScheduleId': REFRESH_SCHEDULE_ID,
                'ScheduleFrequency': {
                    'Interval': 'DAILY',
                    'TimeOfTheDay': '06:00',
                    'Timezone': 'America/New_York'
                },
                'RefreshType': 'FULL_REFRESH'
            }
        )

    try:
        response = retry_with_backoff(_create)
        if response:
            print(f"  ✅ Refresh schedule created: {REFRESH_SCHEDULE_ID}")
            print(f"     Frequency: DAILY at 06:00 America/New_York")
        return True
    except ClientError as e:
        print(f"  ❌ Failed to create refresh schedule: {e}")
        return False


# ============================================================================
# STEP 6: DEPLOYMENT SUMMARY
# ============================================================================

def print_deployment_summary(qs_client):
    """Print final deployment summary with resource status."""
    print("\n" + "=" * 80)
    print("QUICKSIGHT DASHBOARD DEPLOYMENT SUMMARY")
    print("=" * 80)

    resources = [
        ("Athena Data Source", DATA_SOURCE_ID, "data_source"),
        ("Dataset: dim_fund", DATASET_DIM_FUND_ID, "dataset"),
        ("Dataset: dim_category", DATASET_DIM_CATEGORY_ID, "dataset"),
        ("Dataset: dim_date", DATASET_DIM_DATE_ID, "dataset"),
        ("Dataset: fact (joined)", DATASET_FACT_ID, "dataset"),
        ("Analysis", ANALYSIS_ID, "analysis"),
        ("Dashboard", DASHBOARD_ID, "dashboard"),
        ("Refresh Schedule", REFRESH_SCHEDULE_ID, "schedule")
    ]

    print(f"\n{'Resource':<30} | {'ID':<35} | Status")
    print("-" * 80)

    for resource_name, resource_id, resource_type in resources:
        try:
            if resource_type == "data_source":
                qs_client.describe_data_source(AwsAccountId=ACCOUNT_ID, DataSourceId=resource_id)
                status = "✅"
            elif resource_type == "dataset":
                qs_client.describe_data_set(AwsAccountId=ACCOUNT_ID, DataSetId=resource_id)
                status = "✅"
            elif resource_type == "analysis":
                qs_client.describe_analysis(AwsAccountId=ACCOUNT_ID, AnalysisId=resource_id)
                status = "✅"
            elif resource_type == "dashboard":
                qs_client.describe_dashboard(AwsAccountId=ACCOUNT_ID, DashboardId=resource_id)
                status = "✅"
            elif resource_type == "schedule":
                qs_client.describe_refresh_schedule(
                    AwsAccountId=ACCOUNT_ID,
                    DataSetId=DATASET_FACT_ID,
                    ScheduleId=resource_id
                )
                status = "✅"
            else:
                status = "❓"
        except ClientError:
            status = "❌"

        print(f"{resource_name:<30} | {resource_id:<35} | {status}")

    print("\n" + "=" * 80)
    print("Dashboard URL:")
    print(f"https://{AWS_REGION}.quicksight.aws.amazon.com/sn/dashboards/{DASHBOARD_ID}")
    print("=" * 80 + "\n")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function."""
    print("=" * 80)
    print("QUICKSIGHT DASHBOARD SETUP - US MUTUAL FUNDS & ETF")
    print("=" * 80)
    print(f"\nAWS Region: {AWS_REGION}")
    print(f"Account ID: {ACCOUNT_ID}")
    print(f"Author ARN: {QS_AUTHOR_ARN}")
    print(f"Glue Database: {GLUE_DATABASE}")

    # Initialize boto3 client
    qs_client = boto3.client('quicksight', region_name=AWS_REGION)

    # Step 1: Create data source
    if not create_athena_data_source(qs_client):
        print("\n❌ Failed at Step 1 - Data Source creation")
        return 1

    # Step 2: Create datasets
    if not create_dim_fund_dataset(qs_client):
        print("\n❌ Failed at Step 2A - dim_fund dataset creation")
        return 1

    if not create_dim_category_dataset(qs_client):
        print("\n❌ Failed at Step 2B - dim_category dataset creation")
        return 1

    if not create_dim_date_dataset(qs_client):
        print("\n❌ Failed at Step 2C - dim_date dataset creation")
        return 1

    if not create_fact_performance_dataset(qs_client):
        print("\n❌ Failed at Step 2D - fact_performance dataset creation")
        return 1

    # Step 3: Create analysis
    if not create_analysis(qs_client):
        print("\n❌ Failed at Step 3 - Analysis creation")
        return 1

    # Step 4: Publish dashboard
    if not publish_dashboard(qs_client):
        print("\n❌ Failed at Step 4 - Dashboard publishing")
        return 1

    # Step 5: Create refresh schedule
    if not create_refresh_schedule(qs_client):
        print("\n❌ Failed at Step 5 - Refresh schedule creation")
        return 1

    # Step 6: Print summary
    print_deployment_summary(qs_client)

    print("✅ QuickSight dashboard deployment completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
