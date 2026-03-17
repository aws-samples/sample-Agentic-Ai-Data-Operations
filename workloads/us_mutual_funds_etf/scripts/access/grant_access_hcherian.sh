#!/bin/bash
#
# Quick execution script to grant access to demo-role/hcherian-Isengard
# for the US Mutual Funds & ETF workload.
#
# This grants:
# - IAM policy for S3, Glue, Lake Formation, Athena access
# - Lake Formation SELECT permissions on all Gold tables
# - QuickSight dashboard view access
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRINCIPAL="demo-role/hcherian-Isengard"

echo "=========================================="
echo "Granting access to: $PRINCIPAL"
echo "=========================================="
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.11+"
    exit 1
fi

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "ERROR: AWS CLI not configured. Please run 'aws configure' first."
    exit 1
fi

# Execute the access grant script
python3 "$SCRIPT_DIR/grant_access_to_principal.py" \
    --principal "$PRINCIPAL"

EXIT_CODE=$?

echo ""
echo "=========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ ACCESS GRANTED SUCCESSFULLY"
    echo ""
    echo "Principal $PRINCIPAL now has:"
    echo "  • Read access to s3://your-datalake-bucket/"
    echo "  • SELECT access to finsights_gold.* tables"
    echo "  • View access to QuickSight dashboard"
    echo ""
    echo "Next steps:"
    echo "  1. User can query Gold tables via Athena/Redshift Spectrum"
    echo "  2. User can view dashboard at:"
    echo "     https://us-east-1.quicksight.aws.amazon.com/sn/dashboards/finsights-finance-dashboard"
else
    echo "⚠️  ACCESS GRANT COMPLETED WITH WARNINGS"
    echo "  Review the output above for details"
fi
echo "=========================================="

exit $EXIT_CODE
