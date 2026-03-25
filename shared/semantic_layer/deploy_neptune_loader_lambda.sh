#!/bin/bash

###############################################################################
# Deploy Neptune Loader as Lambda Function
# Packages and deploys the semantic layer loader to AWS Lambda
###############################################################################

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
FUNCTION_NAME="${FUNCTION_NAME:-neptune-metadata-loader}"
REGION="${AWS_REGION:-us-east-1}"
RUNTIME="python3.11"
TIMEOUT=900  # 15 minutes
MEMORY=2048

# Get Neptune configuration
if [ ! -f "shared/semantic_layer/neptune_config.sh" ]; then
    echo -e "${YELLOW}⚠️  Neptune config not found. Run setup_neptune.sh first.${NC}"
    exit 1
fi

source shared/semantic_layer/neptune_config.sh

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Deploy Neptune Loader Lambda Function                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Function Name:   $FUNCTION_NAME"
echo "Region:          $REGION"
echo "Runtime:         $RUNTIME"
echo "Timeout:         ${TIMEOUT}s"
echo "Memory:          ${MEMORY}MB"
echo ""

# Step 1: Create deployment package
echo -e "${GREEN}Step 1: Creating deployment package${NC}"
DEPLOY_DIR="/tmp/neptune-loader-deploy"
rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"

# Copy Python code
echo "Copying Python modules..."
mkdir -p "$DEPLOY_DIR/shared"
cp -r shared/schemas "$DEPLOY_DIR/shared/"
cp -r shared/metadata "$DEPLOY_DIR/shared/"
cp -r shared/embeddings "$DEPLOY_DIR/shared/"
cp -r shared/neptune "$DEPLOY_DIR/shared/"
cp -r shared/synodb "$DEPLOY_DIR/shared/"
cp shared/semantic_layer/load_to_neptune.py "$DEPLOY_DIR/"

# Copy workloads directory (needed for semantic.yaml files)
mkdir -p "$DEPLOY_DIR/workloads"
for workload_dir in workloads/*/; do
    workload_name=$(basename "$workload_dir")
    mkdir -p "$DEPLOY_DIR/workloads/$workload_name/config"
    if [ -f "workloads/$workload_name/config/semantic.yaml" ]; then
        cp "workloads/$workload_name/config/semantic.yaml" "$DEPLOY_DIR/workloads/$workload_name/config/"
    fi
done

# Create Lambda handler
cat > "$DEPLOY_DIR/lambda_handler.py" << 'EOF'
import json
import os
import sys

# Add shared modules to path
sys.path.insert(0, '/var/task')

from load_to_neptune import NeptuneLoadingPipeline

def lambda_handler(event, context):
    """
    Lambda handler for Neptune metadata loading.

    Event parameters:
    - workload: Workload name (e.g., financial_portfolios)
    - database: Glue database name
    - neptune_endpoint: Neptune cluster endpoint
    - region: AWS region (default: us-east-1)
    - clear_graph: Clear existing graph (default: false)
    """

    workload = event.get('workload')
    database = event.get('database')
    neptune_endpoint = event.get('neptune_endpoint')
    region = event.get('region', 'us-east-1')
    clear_graph = event.get('clear_graph', False)

    if not workload or not database or not neptune_endpoint:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Missing required parameters: workload, database, neptune_endpoint'
            })
        }

    try:
        # Run loading pipeline
        pipeline = NeptuneLoadingPipeline(
            workload=workload,
            database=database,
            neptune_endpoint=neptune_endpoint,
            region=region,
            dry_run=False
        )

        result = pipeline.run(clear_graph=clear_graph)

        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'workload': workload,
                'database': database
            })
        }
EOF

# Install dependencies
echo "Installing Python dependencies..."
pip3 install --target "$DEPLOY_DIR" \
    gremlinpython \
    pyyaml \
    boto3 \
    --quiet

# Create zip
echo "Creating deployment zip..."
cd "$DEPLOY_DIR"
zip -r /tmp/neptune-loader.zip . -q
cd - > /dev/null

echo -e "${GREEN}✓ Deployment package created: /tmp/neptune-loader.zip${NC}"

# Step 2: Create IAM role (if needed)
echo ""
echo -e "${GREEN}Step 2: Checking IAM role${NC}"

ROLE_NAME="NeptuneLoaderLambdaRole"
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text 2>/dev/null || echo "")

if [ -z "$ROLE_ARN" ]; then
    echo "Creating IAM role: $ROLE_NAME"

    # Create trust policy
    cat > /tmp/lambda-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    # Create role
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document file:///tmp/lambda-trust-policy.json

    # Attach policies
    aws iam attach-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"

    aws iam attach-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-arn "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"

    # Inline policy for Glue/LF/Bedrock
    cat > /tmp/lambda-inline-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "lakeformation:GetResourceLFTags",
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    }
  ]
}
EOF

    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "NeptuneLoaderPolicy" \
        --policy-document file:///tmp/lambda-inline-policy.json

    # Wait for role propagation
    echo "Waiting for IAM role to propagate (10s)..."
    sleep 10

    ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)
fi

echo -e "${GREEN}✓ IAM role ready: $ROLE_ARN${NC}"

# Step 3: Create or update Lambda function
echo ""
echo -e "${GREEN}Step 3: Deploying Lambda function${NC}"

# Check if function exists
FUNCTION_EXISTS=$(aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" 2>/dev/null || echo "")

if [ -z "$FUNCTION_EXISTS" ]; then
    echo "Creating Lambda function..."

    # Get subnet IDs and security group from Neptune config
    SUBNET_IDS=$(aws neptune describe-db-subnet-groups \
        --db-subnet-group-name "neptune-subnet-group-$REGION" \
        --region "$REGION" \
        --query 'DBSubnetGroups[0].Subnets[*].SubnetIdentifier' \
        --output text | tr '\t' ',')

    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --role "$ROLE_ARN" \
        --handler lambda_handler.lambda_handler \
        --timeout "$TIMEOUT" \
        --memory-size "$MEMORY" \
        --zip-file fileb:///tmp/neptune-loader.zip \
        --vpc-config "SubnetIds=${SUBNET_IDS},SecurityGroupIds=${NEPTUNE_SECURITY_GROUP}" \
        --region "$REGION" \
        --environment "Variables={NEPTUNE_ENDPOINT=${NEPTUNE_ENDPOINT},NEPTUNE_REGION=${REGION}}"

    echo -e "${GREEN}✓ Lambda function created${NC}"
else
    echo "Updating Lambda function code..."

    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb:///tmp/neptune-loader.zip \
        --region "$REGION"

    echo -e "${GREEN}✓ Lambda function updated${NC}"
fi

# Step 4: Test invocation
echo ""
echo -e "${GREEN}Step 4: Lambda function deployed!${NC}"
echo ""
echo "To invoke the function:"
echo ""
echo "aws lambda invoke \\"
echo "  --function-name $FUNCTION_NAME \\"
echo "  --region $REGION \\"
echo "  --payload '{\"workload\":\"financial_portfolios\",\"database\":\"financial_portfolios_db\",\"neptune_endpoint\":\"${NEPTUNE_ENDPOINT}\",\"region\":\"${REGION}\"}' \\"
echo "  /tmp/output.json"
echo ""
echo "cat /tmp/output.json | jq ."
echo ""

# Cleanup
rm -rf "$DEPLOY_DIR"
rm -f /tmp/neptune-loader.zip
rm -f /tmp/lambda-trust-policy.json
rm -f /tmp/lambda-inline-policy.json
