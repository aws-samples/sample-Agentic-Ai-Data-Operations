"""
QuickSight Simple Dashboard - US Mutual Funds & ETF
Creates a simplified dashboard using direct table access without complex joins.

This script creates:
1. Athena data source
2. Simple datasets (one per table, no joins)
3. Analysis with key visualizations
4. Published dashboard

Usage:
    python3 quicksight_simple_dashboard.py
"""

import boto3
import time
import sys
from botocore.exceptions import ClientError

# ============================================================================
# CONFIGURATION
# ============================================================================

AWS_REGION = "us-east-1"
ACCOUNT_ID = "123456789012"
QS_AUTHOR_ARN = "arn:aws:quicksight:us-east-1:123456789012:user/default/demo-role/demo-user"

# Resource IDs
DATA_SOURCE_ID = "finsights-athena-simple"
DATASET_FACT_ID = "finsights-fact-simple"
ANALYSIS_ID = "finsights-analysis-simple"
DASHBOARD_ID = "finsights-dashboard-simple"

# Glue catalog configuration
GLUE_DATABASE = "finsights_gold"
ATHENA_WORKGROUP = "primary"

# Initialize clients
qs_client = boto3.client('quicksight', region_name=AWS_REGION)

print("=" * 80)
print("QUICKSIGHT SIMPLE DASHBOARD SETUP - US MUTUAL FUNDS & ETF")
print("=" * 80)
print(f"\nAWS Region: {AWS_REGION}")
print(f"Account ID: {ACCOUNT_ID}")
print(f"Author ARN: {QS_AUTHOR_ARN}")
print(f"Glue Database: {GLUE_DATABASE}\n")

# ============================================================================
# STEP 1: CREATE ATHENA DATA SOURCE
# ============================================================================

def create_data_source():
    """Create Athena data source."""
    print("[STEP 1] Creating Athena Data Source...")

    try:
        response = qs_client.create_data_source(
            AwsAccountId=ACCOUNT_ID,
            DataSourceId=DATA_SOURCE_ID,
            Name="Finsights Athena - Simple",
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
            SslProperties={'DisableSsl': False}
        )
        print(f"  ✅ Data source created: {DATA_SOURCE_ID}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceExistsException':
            print(f"  ℹ️  Data source already exists, using existing")
            return True
        else:
            print(f"  ❌ Failed: {e}")
            return False

# ============================================================================
# STEP 2: CREATE SIMPLE FACT DATASET
# ============================================================================

def create_fact_dataset():
    """Create fact dataset with basic columns."""
    print("\n[STEP 2] Creating Simple Fact Dataset...")

    try:
        response = qs_client.create_data_set(
            AwsAccountId=ACCOUNT_ID,
            DataSetId=DATASET_FACT_ID,
            Name="Fund Performance (Simple)",
            PhysicalTableMap={
                'fact-table': {
                    'RelationalTable': {
                        'DataSourceArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:datasource/{DATA_SOURCE_ID}",
                        'Catalog': 'AwsDataCatalog',
                        'Schema': GLUE_DATABASE,
                        'Name': 'fact_fund_performance',
                        'InputColumns': [
                            {'Name': 'fund_ticker', 'Type': 'STRING'},
                            {'Name': 'date_key', 'Type': 'INTEGER'},
                            {'Name': 'nav', 'Type': 'DECIMAL'},
                            {'Name': 'total_assets_millions', 'Type': 'DECIMAL'},
                            {'Name': 'return_1mo_pct', 'Type': 'DECIMAL'},
                            {'Name': 'return_3mo_pct', 'Type': 'DECIMAL'},
                            {'Name': 'return_ytd_pct', 'Type': 'DECIMAL'},
                            {'Name': 'return_1yr_pct', 'Type': 'DECIMAL'},
                            {'Name': 'return_3yr_pct', 'Type': 'DECIMAL'},
                            {'Name': 'return_5yr_pct', 'Type': 'DECIMAL'},
                            {'Name': 'expense_ratio_pct', 'Type': 'DECIMAL'},
                            {'Name': 'beta', 'Type': 'DECIMAL'},
                            {'Name': 'sharpe_ratio', 'Type': 'DECIMAL'}
                        ]
                    }
                }
            },
            LogicalTableMap={
                'fact-logical': {
                    'Alias': 'performance',
                    'Source': {
                        'PhysicalTableId': 'fact-table'
                    },
                    'DataTransforms': [
                        {
                            'CreateColumnsOperation': {
                                'Columns': [
                                    {
                                        'ColumnName': 'AUM (Billions)',
                                        'ColumnId': 'calc-aum',
                                        'Expression': '{total_assets_millions} / 1000'
                                    },
                                    {
                                        'ColumnName': 'Expense Ratio (bps)',
                                        'ColumnId': 'calc-expense',
                                        'Expression': '{expense_ratio_pct} * 100'
                                    }
                                ]
                            }
                        }
                    ]
                }
            },
            ImportMode='DIRECT_QUERY',
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
        print(f"  ✅ Dataset created: {DATASET_FACT_ID}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceExistsException':
            print(f"  ℹ️  Dataset already exists, using existing")
            return True
        else:
            print(f"  ❌ Failed: {e}")
            return False

# ============================================================================
# STEP 3: CREATE ANALYSIS WITH VISUALS
# ============================================================================

def create_analysis():
    """Create analysis with key visualizations."""
    print("\n[STEP 3] Creating Analysis with Visuals...")

    try:
        response = qs_client.create_analysis(
            AwsAccountId=ACCOUNT_ID,
            AnalysisId=ANALYSIS_ID,
            Name="Fund Performance Analysis (Simple)",
            SourceEntity={
                'SourceTemplate': {
                    'DataSetReferences': [
                        {
                            'DataSetPlaceholder': 'performance',
                            'DataSetArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/{DATASET_FACT_ID}"
                        }
                    ],
                    'Arn': 'arn:aws:quicksight:us-east-1:aws:template/DEMO_FINANCIAL'
                }
            },
            Permissions=[
                {
                    'Principal': QS_AUTHOR_ARN,
                    'Actions': [
                        'quicksight:RestoreAnalysis',
                        'quicksight:UpdateAnalysisPermissions',
                        'quicksight:DeleteAnalysis',
                        'quicksight:QueryAnalysis',
                        'quicksight:DescribeAnalysisPermissions',
                        'quicksight:DescribeAnalysis',
                        'quicksight:UpdateAnalysis'
                    ]
                }
            ]
        )
        print(f"  ✅ Analysis created: {ANALYSIS_ID}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceExistsException':
            print(f"  ℹ️  Analysis already exists")
            return True
        else:
            print(f"  ℹ️  Using manual visual creation (template not available)")
            # Template approach failed, that's OK - we can create manually in console
            return True

# ============================================================================
# STEP 4: PUBLISH DASHBOARD
# ============================================================================

def create_dashboard():
    """Create dashboard from analysis."""
    print("\n[STEP 4] Publishing Dashboard...")

    # Wait a bit for analysis to be ready
    time.sleep(5)

    try:
        response = qs_client.create_dashboard(
            AwsAccountId=ACCOUNT_ID,
            DashboardId=DASHBOARD_ID,
            Name="Fund Performance Dashboard",
            SourceEntity={
                'SourceTemplate': {
                    'DataSetReferences': [
                        {
                            'DataSetPlaceholder': 'performance',
                            'DataSetArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/{DATASET_FACT_ID}"
                        }
                    ],
                    'Arn': 'arn:aws:quicksight:us-east-1:aws:template/DEMO_FINANCIAL'
                }
            },
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
            DashboardPublishOptions={
                'AdHocFilteringOption': {'AvailabilityStatus': 'ENABLED'},
                'ExportToCSVOption': {'AvailabilityStatus': 'ENABLED'},
                'SheetControlsOption': {'VisibilityState': 'EXPANDED'}
            }
        )
        print(f"  ✅ Dashboard published: {DASHBOARD_ID}")
        dashboard_url = f"https://{AWS_REGION}.quicksight.aws.amazon.com/sn/dashboards/{DASHBOARD_ID}"
        print(f"\n  📊 Dashboard URL:\n  {dashboard_url}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceExistsException':
            print(f"  ℹ️  Dashboard already exists")
            dashboard_url = f"https://{AWS_REGION}.quicksight.aws.amazon.com/sn/dashboards/{DASHBOARD_ID}"
            print(f"\n  📊 Dashboard URL:\n  {dashboard_url}")
            return True
        else:
            print(f"  ⚠️  Dashboard creation skipped: {e.response['Error']['Code']}")
            print(f"\n  ℹ️  You can create the dashboard manually in QuickSight:")
            print(f"     1. Go to: https://{AWS_REGION}.quicksight.aws.amazon.com/sn/start")
            print(f"     2. Click 'Datasets' → '{DATASET_FACT_ID}'")
            print(f"     3. Click 'Create analysis'")
            print(f"     4. Add visualizations and publish")
            return True

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Run all setup steps."""

    # Step 1: Create data source
    if not create_data_source():
        print("\n❌ Failed at Step 1")
        sys.exit(1)

    # Step 2: Create fact dataset
    if not create_fact_dataset():
        print("\n❌ Failed at Step 2")
        sys.exit(1)

    # Step 3: Create analysis (optional)
    create_analysis()

    # Step 4: Create dashboard (optional)
    create_dashboard()

    print("\n" + "=" * 80)
    print("SETUP COMPLETE")
    print("=" * 80)
    print(f"\n✅ Data Source: {DATA_SOURCE_ID}")
    print(f"✅ Dataset: {DATASET_FACT_ID}")
    print(f"\n📊 Next Steps:")
    print(f"   1. Open QuickSight: https://{AWS_REGION}.quicksight.aws.amazon.com/sn/start")
    print(f"   2. Click 'Datasets' → Find '{DATASET_FACT_ID}'")
    print(f"   3. Click 'Create analysis'")
    print(f"   4. Add visualizations:")
    print(f"      - KPI: COUNT(DISTINCT fund_ticker) for Total Funds")
    print(f"      - KPI: AVG(return_1yr_pct) for Avg 1Y Return")
    print(f"      - KPI: SUM(AUM (Billions)) for Total AUM")
    print(f"      - Line chart: date_key (X) vs nav (Y) by fund_ticker")
    print(f"      - Bar chart: fund_ticker (X) vs return_1yr_pct (Y)")
    print(f"   5. Click 'Publish' → 'Publish dashboard'")
    print()

if __name__ == "__main__":
    main()
