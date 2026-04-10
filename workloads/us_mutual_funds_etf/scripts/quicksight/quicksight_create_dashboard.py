"""
QuickSight Dashboard Creator - US Mutual Funds & ETF
Creates analysis and dashboard programmatically with defined visuals.
"""

import boto3
import time
import json
from botocore.exceptions import ClientError

# Configuration
AWS_REGION = "us-east-1"
ACCOUNT_ID = "123456789012"
QS_AUTHOR_ARN = os.environ.get("QS_AUTHOR_ARN", f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:user/default/demo-role/demo-user")

DATASET_ID = "finsights-fact-simple"
ANALYSIS_ID = "finsights-analysis-v2"
DASHBOARD_ID = "finsights-dashboard-v2"

qs_client = boto3.client('quicksight', region_name=AWS_REGION)

print("=" * 80)
print("CREATING QUICKSIGHT DASHBOARD")
print("=" * 80)

# ============================================================================
# STEP 1: CREATE ANALYSIS WITH VISUALS
# ============================================================================

def create_analysis_with_visuals():
    """Create analysis with defined visuals."""
    print("\n[STEP 1] Creating Analysis with Visuals...")

    dataset_arn = f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/{DATASET_ID}"

    # Define the analysis structure
    definition = {
        'DataSetIdentifierDeclarations': [
            {
                'Identifier': 'performance',
                'DataSetArn': dataset_arn
            }
        ],
        'Sheets': [
            {
                'SheetId': 'sheet1',
                'Name': 'Fund Performance Overview',
                'Visuals': [
                    # Visual 1: Total Funds KPI
                    {
                        'KPIVisual': {
                            'VisualId': 'kpi-total-funds',
                            'Title': {
                                'Visibility': 'VISIBLE',
                                'FormatText': {
                                    'PlainText': 'Total Funds'
                                }
                            },
                            'ChartConfiguration': {
                                'FieldWells': {
                                    'Values': [
                                        {
                                            'CategoricalMeasureField': {
                                                'FieldId': 'total-funds',
                                                'Column': {
                                                    'DataSetIdentifier': 'performance',
                                                    'ColumnName': 'fund_ticker'
                                                },
                                                'AggregationFunction': 'DISTINCT_COUNT'
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    },
                    # Visual 2: Avg 1Y Return KPI
                    {
                        'KPIVisual': {
                            'VisualId': 'kpi-avg-return',
                            'Title': {
                                'Visibility': 'VISIBLE',
                                'FormatText': {
                                    'PlainText': 'Avg 1Y Return (%)'
                                }
                            },
                            'ChartConfiguration': {
                                'FieldWells': {
                                    'Values': [
                                        {
                                            'NumericalMeasureField': {
                                                'FieldId': 'avg-return',
                                                'Column': {
                                                    'DataSetIdentifier': 'performance',
                                                    'ColumnName': 'return_1yr_pct'
                                                },
                                                'AggregationFunction': {
                                                    'SimpleNumericalAggregation': 'AVERAGE'
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    },
                    # Visual 3: Total AUM KPI
                    {
                        'KPIVisual': {
                            'VisualId': 'kpi-total-aum',
                            'Title': {
                                'Visibility': 'VISIBLE',
                                'FormatText': {
                                    'PlainText': 'Total AUM (Billions)'
                                }
                            },
                            'ChartConfiguration': {
                                'FieldWells': {
                                    'Values': [
                                        {
                                            'NumericalMeasureField': {
                                                'FieldId': 'total-aum',
                                                'Column': {
                                                    'DataSetIdentifier': 'performance',
                                                    'ColumnName': 'total_assets_millions'
                                                },
                                                'AggregationFunction': {
                                                    'SimpleNumericalAggregation': 'SUM'
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    },
                    # Visual 4: Top Performers Bar Chart
                    {
                        'BarChartVisual': {
                            'VisualId': 'bar-top-performers',
                            'Title': {
                                'Visibility': 'VISIBLE',
                                'FormatText': {
                                    'PlainText': 'Top 10 Funds by 1Y Return'
                                }
                            },
                            'ChartConfiguration': {
                                'FieldWells': {
                                    'BarChartAggregatedFieldWells': {
                                        'Category': [
                                            {
                                                'CategoricalDimensionField': {
                                                    'FieldId': 'fund-ticker',
                                                    'Column': {
                                                        'DataSetIdentifier': 'performance',
                                                        'ColumnName': 'fund_ticker'
                                                    }
                                                }
                                            }
                                        ],
                                        'Values': [
                                            {
                                                'NumericalMeasureField': {
                                                    'FieldId': 'return-value',
                                                    'Column': {
                                                        'DataSetIdentifier': 'performance',
                                                        'ColumnName': 'return_1yr_pct'
                                                    },
                                                    'AggregationFunction': {
                                                        'SimpleNumericalAggregation': 'AVERAGE'
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                },
                                'Orientation': 'HORIZONTAL'
                            }
                        }
                    },
                    # Visual 5: Returns Table
                    {
                        'TableVisual': {
                            'VisualId': 'table-returns',
                            'Title': {
                                'Visibility': 'VISIBLE',
                                'FormatText': {
                                    'PlainText': 'Fund Performance Summary'
                                }
                            },
                            'ChartConfiguration': {
                                'FieldWells': {
                                    'TableAggregatedFieldWells': {
                                        'GroupBy': [
                                            {
                                                'CategoricalDimensionField': {
                                                    'FieldId': 'fund',
                                                    'Column': {
                                                        'DataSetIdentifier': 'performance',
                                                        'ColumnName': 'fund_ticker'
                                                    }
                                                }
                                            }
                                        ],
                                        'Values': [
                                            {
                                                'NumericalMeasureField': {
                                                    'FieldId': 'return-1mo',
                                                    'Column': {
                                                        'DataSetIdentifier': 'performance',
                                                        'ColumnName': 'return_1mo_pct'
                                                    },
                                                    'AggregationFunction': {
                                                        'SimpleNumericalAggregation': 'AVERAGE'
                                                    }
                                                }
                                            },
                                            {
                                                'NumericalMeasureField': {
                                                    'FieldId': 'return-3mo',
                                                    'Column': {
                                                        'DataSetIdentifier': 'performance',
                                                        'ColumnName': 'return_3mo_pct'
                                                    },
                                                    'AggregationFunction': {
                                                        'SimpleNumericalAggregation': 'AVERAGE'
                                                    }
                                                }
                                            },
                                            {
                                                'NumericalMeasureField': {
                                                    'FieldId': 'return-1yr',
                                                    'Column': {
                                                        'DataSetIdentifier': 'performance',
                                                        'ColumnName': 'return_1yr_pct'
                                                    },
                                                    'AggregationFunction': {
                                                        'SimpleNumericalAggregation': 'AVERAGE'
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        ]
    }

    try:
        response = qs_client.create_analysis(
            AwsAccountId=ACCOUNT_ID,
            AnalysisId=ANALYSIS_ID,
            Name="Fund Performance Analysis",
            Definition=definition,
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
        print(f"     ARN: {response['Arn']}")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceExistsException':
            print(f"  ℹ️  Analysis already exists")
            return True
        else:
            print(f"  ❌ Failed: {error_code}")
            print(f"     Message: {e.response['Error']['Message']}")
            return False

# ============================================================================
# STEP 2: PUBLISH DASHBOARD
# ============================================================================

def publish_dashboard():
    """Publish dashboard from analysis."""
    print("\n[STEP 2] Publishing Dashboard...")

    # Wait for analysis to be ready
    time.sleep(3)

    try:
        response = qs_client.create_dashboard(
            AwsAccountId=ACCOUNT_ID,
            DashboardId=DASHBOARD_ID,
            Name="Fund Performance Dashboard",
            SourceEntity={
                'SourceAnalysis': {
                    'Arn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:analysis/{ANALYSIS_ID}",
                    'DataSetReferences': [
                        {
                            'DataSetPlaceholder': 'performance',
                            'DataSetArn': f"arn:aws:quicksight:{AWS_REGION}:{ACCOUNT_ID}:dataset/{DATASET_ID}"
                        }
                    ]
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
        print(f"     ARN: {response['Arn']}")
        dashboard_url = f"https://{AWS_REGION}.quicksight.aws.amazon.com/sn/dashboards/{DASHBOARD_ID}"
        print(f"\n  📊 Dashboard URL:")
        print(f"     {dashboard_url}")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceExistsException':
            print(f"  ℹ️  Dashboard already exists")
            dashboard_url = f"https://{AWS_REGION}.quicksight.aws.amazon.com/sn/dashboards/{DASHBOARD_ID}"
            print(f"\n  📊 Dashboard URL:")
            print(f"     {dashboard_url}")
            return True
        else:
            print(f"  ❌ Failed: {error_code}")
            print(f"     Message: {e.response['Error']['Message']}")
            return False

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run dashboard creation."""

    # Step 1: Create analysis
    if not create_analysis_with_visuals():
        print("\n⚠️  Analysis creation failed, but continuing...")

    # Step 2: Publish dashboard
    if not publish_dashboard():
        print("\n❌ Dashboard creation failed")
        print("\n📋 Manual alternative:")
        print(f"   1. Go to: https://{AWS_REGION}.quicksight.aws.amazon.com/sn/start")
        print(f"   2. Click 'Analyses' → Find '{ANALYSIS_ID}' (if exists)")
        print(f"   3. Click 'Share' → 'Publish dashboard'")
        print(f"   4. Or create new analysis from dataset '{DATASET_ID}'")
        return

    print("\n" + "=" * 80)
    print("DASHBOARD DEPLOYMENT COMPLETE")
    print("=" * 80)
    print(f"\n✅ Analysis: {ANALYSIS_ID}")
    print(f"✅ Dashboard: {DASHBOARD_ID}")
    print(f"\n📊 Access your dashboard:")
    print(f"   https://{AWS_REGION}.quicksight.aws.amazon.com/sn/dashboards/{DASHBOARD_ID}")
    print()

if __name__ == "__main__":
    main()
