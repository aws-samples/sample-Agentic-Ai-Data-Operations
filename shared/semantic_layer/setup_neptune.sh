#!/bin/bash

###############################################################################
# Neptune Cluster Setup Script
# Creates Neptune cluster for semantic layer knowledge graph
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CLUSTER_ID="${CLUSTER_ID:-semantic-layer-cluster}"
INSTANCE_ID="${INSTANCE_ID:-semantic-layer-instance}"
INSTANCE_CLASS="${INSTANCE_CLASS:-db.t3.medium}"
REGION="${AWS_REGION:-us-east-1}"
ENGINE="neptune"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Neptune Cluster Setup for Semantic Layer              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Cluster ID:       $CLUSTER_ID"
echo "  Instance ID:      $INSTANCE_ID"
echo "  Instance Class:   $INSTANCE_CLASS"
echo "  Region:           $REGION"
echo ""

# Function to print step headers
step() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for status
wait_for_status() {
    local resource_type=$1
    local resource_id=$2
    local target_status=$3
    local max_wait=$4
    local elapsed=0

    echo -e "${YELLOW}Waiting for $resource_type to reach status: $target_status${NC}"

    while [ $elapsed -lt $max_wait ]; do
        if [ "$resource_type" == "cluster" ]; then
            status=$(aws neptune describe-db-clusters \
                --db-cluster-identifier "$resource_id" \
                --region "$REGION" \
                --query 'DBClusters[0].Status' \
                --output text 2>/dev/null || echo "not-found")
        else
            status=$(aws neptune describe-db-instances \
                --db-instance-identifier "$resource_id" \
                --region "$REGION" \
                --query 'DBInstances[0].DBInstanceStatus' \
                --output text 2>/dev/null || echo "not-found")
        fi

        echo -n "."

        if [ "$status" == "$target_status" ]; then
            echo ""
            echo -e "${GREEN}✓ $resource_type is $target_status${NC}"
            return 0
        fi

        sleep 10
        elapsed=$((elapsed + 10))
    done

    echo ""
    echo -e "${RED}✗ Timeout waiting for $resource_type${NC}"
    return 1
}

###############################################################################
# STEP 1: Check Prerequisites
###############################################################################

step "STEP 1: Checking Prerequisites"

# Check AWS CLI
if ! command_exists aws; then
    echo -e "${RED}✗ AWS CLI not found${NC}"
    echo "Install: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    exit 1
fi
echo -e "${GREEN}✓ AWS CLI installed${NC}"

# Check AWS credentials
if ! aws sts get-caller-identity --region "$REGION" &>/dev/null; then
    echo -e "${RED}✗ AWS credentials not configured${NC}"
    echo "Run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
USER_ARN=$(aws sts get-caller-identity --query Arn --output text)
echo -e "${GREEN}✓ AWS credentials configured${NC}"
echo "  Account: $ACCOUNT_ID"
echo "  User:    $USER_ARN"

# Check if cluster already exists
echo ""
echo "Checking if Neptune cluster already exists..."
if aws neptune describe-db-clusters \
    --db-cluster-identifier "$CLUSTER_ID" \
    --region "$REGION" &>/dev/null; then

    echo -e "${YELLOW}⚠️  Cluster '$CLUSTER_ID' already exists!${NC}"
    echo ""

    ENDPOINT=$(aws neptune describe-db-clusters \
        --db-cluster-identifier "$CLUSTER_ID" \
        --region "$REGION" \
        --query 'DBClusters[0].Endpoint' \
        --output text)

    STATUS=$(aws neptune describe-db-clusters \
        --db-cluster-identifier "$CLUSTER_ID" \
        --region "$REGION" \
        --query 'DBClusters[0].Status' \
        --output text)

    echo "  Status:   $STATUS"
    echo "  Endpoint: $ENDPOINT"
    echo ""
    echo "Options:"
    echo "  1. Use existing cluster"
    echo "  2. Delete and recreate"
    echo "  3. Exit"
    echo ""
    read -p "Choose (1/2/3): " choice

    case $choice in
        1)
            echo -e "${GREEN}Using existing cluster${NC}"
            echo ""
            echo "Neptune Endpoint: $ENDPOINT"
            echo ""
            echo "Run load job:"
            echo "  python shared/semantic_layer/load_to_neptune.py \\"
            echo "    --workload financial_portfolios \\"
            echo "    --database financial_portfolios_db \\"
            echo "    --neptune-endpoint $ENDPOINT \\"
            echo "    --region $REGION"
            exit 0
            ;;
        2)
            echo -e "${RED}Deleting existing cluster...${NC}"

            # Delete instance first
            INSTANCES=$(aws neptune describe-db-instances \
                --region "$REGION" \
                --query "DBInstances[?DBClusterIdentifier=='$CLUSTER_ID'].DBInstanceIdentifier" \
                --output text)

            for instance in $INSTANCES; do
                echo "Deleting instance: $instance"
                aws neptune delete-db-instance \
                    --db-instance-identifier "$instance" \
                    --region "$REGION" \
                    --skip-final-snapshot
            done

            echo "Waiting for instances to be deleted..."
            sleep 30

            # Delete cluster
            echo "Deleting cluster: $CLUSTER_ID"
            aws neptune delete-db-cluster \
                --db-cluster-identifier "$CLUSTER_ID" \
                --region "$REGION" \
                --skip-final-snapshot

            echo "Waiting for cluster to be deleted..."
            sleep 60

            echo -e "${GREEN}✓ Cluster deleted${NC}"
            ;;
        3)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            exit 1
            ;;
    esac
fi

###############################################################################
# STEP 2: Get VPC and Subnet Information
###############################################################################

step "STEP 2: Getting VPC and Subnet Information"

# Get default VPC
VPC_ID=$(aws ec2 describe-vpcs \
    --region "$REGION" \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text)

if [ "$VPC_ID" == "None" ] || [ -z "$VPC_ID" ]; then
    echo -e "${RED}✗ No default VPC found${NC}"
    echo "Creating VPC is beyond this script. Please create a VPC first."
    exit 1
fi

echo -e "${GREEN}✓ Found VPC: $VPC_ID${NC}"

# Get subnets in at least 2 availability zones
SUBNET_IDS=$(aws ec2 describe-subnets \
    --region "$REGION" \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=default-for-az,Values=true" \
    --query 'Subnets[].SubnetId' \
    --output text | tr '\t' ',')

if [ -z "$SUBNET_IDS" ]; then
    echo -e "${RED}✗ No subnets found in VPC${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Found subnets: $SUBNET_IDS${NC}"

# Get or create DB subnet group
SUBNET_GROUP_NAME="neptune-subnet-group-$REGION"
echo ""
echo "Checking for DB subnet group..."

if ! aws neptune describe-db-subnet-groups \
    --db-subnet-group-name "$SUBNET_GROUP_NAME" \
    --region "$REGION" &>/dev/null; then

    echo "Creating DB subnet group: $SUBNET_GROUP_NAME"
    aws neptune create-db-subnet-group \
        --db-subnet-group-name "$SUBNET_GROUP_NAME" \
        --db-subnet-group-description "Neptune subnet group for semantic layer" \
        --subnet-ids ${SUBNET_IDS//,/ } \
        --region "$REGION"

    echo -e "${GREEN}✓ Created DB subnet group${NC}"
else
    echo -e "${GREEN}✓ DB subnet group exists${NC}"
fi

###############################################################################
# STEP 3: Create Security Group
###############################################################################

step "STEP 3: Creating Security Group"

SG_NAME="neptune-semantic-layer-sg"
echo "Checking for security group..."

# Check if security group exists
SG_ID=$(aws ec2 describe-security-groups \
    --region "$REGION" \
    --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null)

if [ "$SG_ID" == "None" ] || [ -z "$SG_ID" ]; then
    echo "Creating security group: $SG_NAME"

    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SG_NAME" \
        --description "Security group for Neptune semantic layer" \
        --vpc-id "$VPC_ID" \
        --region "$REGION" \
        --query 'GroupId' \
        --output text)

    echo -e "${GREEN}✓ Created security group: $SG_ID${NC}"

    # Add inbound rule for Neptune port (8182)
    echo "Adding inbound rule for port 8182..."
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 8182 \
        --cidr 0.0.0.0/0 \
        --region "$REGION"

    echo -e "${GREEN}✓ Added inbound rule for port 8182${NC}"
else
    echo -e "${GREEN}✓ Security group exists: $SG_ID${NC}"
fi

###############################################################################
# STEP 4: Create Neptune Cluster
###############################################################################

step "STEP 4: Creating Neptune Cluster"

echo "Creating Neptune DB cluster: $CLUSTER_ID"
echo "This will take 5-10 minutes..."
echo ""

aws neptune create-db-cluster \
    --db-cluster-identifier "$CLUSTER_ID" \
    --engine "$ENGINE" \
    --engine-version "1.2.1.0" \
    --db-subnet-group-name "$SUBNET_GROUP_NAME" \
    --vpc-security-group-ids "$SG_ID" \
    --enable-iam-database-authentication \
    --region "$REGION" \
    --tags "Key=Project,Value=SemanticLayer" "Key=Purpose,Value=KnowledgeGraph"

echo -e "${GREEN}✓ Cluster creation initiated${NC}"

# Wait for cluster to be available
wait_for_status "cluster" "$CLUSTER_ID" "available" 600

###############################################################################
# STEP 5: Create Neptune Instance
###############################################################################

step "STEP 5: Creating Neptune Instance"

echo "Creating Neptune DB instance: $INSTANCE_ID"
echo "This will take 5-10 minutes..."
echo ""

aws neptune create-db-instance \
    --db-instance-identifier "$INSTANCE_ID" \
    --db-instance-class "$INSTANCE_CLASS" \
    --engine "$ENGINE" \
    --db-cluster-identifier "$CLUSTER_ID" \
    --region "$REGION" \
    --tags "Key=Project,Value=SemanticLayer"

echo -e "${GREEN}✓ Instance creation initiated${NC}"

# Wait for instance to be available
wait_for_status "instance" "$INSTANCE_ID" "available" 600

###############################################################################
# STEP 6: Get Cluster Information
###############################################################################

step "STEP 6: Getting Cluster Information"

ENDPOINT=$(aws neptune describe-db-clusters \
    --db-cluster-identifier "$CLUSTER_ID" \
    --region "$REGION" \
    --query 'DBClusters[0].Endpoint' \
    --output text)

READER_ENDPOINT=$(aws neptune describe-db-clusters \
    --db-cluster-identifier "$CLUSTER_ID" \
    --region "$REGION" \
    --query 'DBClusters[0].ReaderEndpoint' \
    --output text)

PORT=$(aws neptune describe-db-clusters \
    --db-cluster-identifier "$CLUSTER_ID" \
    --region "$REGION" \
    --query 'DBClusters[0].Port' \
    --output text)

echo -e "${GREEN}✓ Neptune cluster is ready!${NC}"
echo ""
echo "Cluster Details:"
echo "  Cluster ID:       $CLUSTER_ID"
echo "  Instance ID:      $INSTANCE_ID"
echo "  Instance Class:   $INSTANCE_CLASS"
echo "  Region:           $REGION"
echo "  Writer Endpoint:  $ENDPOINT"
echo "  Reader Endpoint:  $READER_ENDPOINT"
echo "  Port:             $PORT"
echo "  Security Group:   $SG_ID"
echo ""

###############################################################################
# STEP 7: Test Connection
###############################################################################

step "STEP 7: Testing Connection"

echo "Testing connectivity to Neptune..."
echo ""

# Try to connect using gremlin
if command_exists python3; then
    cat > /tmp/test_neptune.py << 'EOF'
#!/usr/bin/env python3
import sys
try:
    from gremlin_python.driver import client

    endpoint = sys.argv[1]

    print(f"Connecting to: wss://{endpoint}:8182/gremlin")
    g = client.Client(f'wss://{endpoint}:8182/gremlin', 'g')

    # Test query
    result = g.submit("g.V().count()").all().result()
    print(f"✓ Connection successful!")
    print(f"  Vertex count: {result[0]}")

    g.close()
    sys.exit(0)

except ImportError:
    print("⚠️  gremlin_python not installed")
    print("   Install: pip install gremlinpython")
    sys.exit(1)
except Exception as e:
    print(f"✗ Connection failed: {e}")
    sys.exit(1)
EOF

    chmod +x /tmp/test_neptune.py
    python3 /tmp/test_neptune.py "$ENDPOINT" || true
    rm /tmp/test_neptune.py
else
    echo -e "${YELLOW}⚠️  Python3 not found, skipping connection test${NC}"
fi

###############################################################################
# STEP 8: Save Configuration
###############################################################################

step "STEP 8: Saving Configuration"

CONFIG_FILE="shared/semantic_layer/neptune_config.sh"

cat > "$CONFIG_FILE" << EOF
#!/bin/bash
# Neptune Configuration
# Generated: $(date)

export NEPTUNE_CLUSTER_ID="$CLUSTER_ID"
export NEPTUNE_INSTANCE_ID="$INSTANCE_ID"
export NEPTUNE_ENDPOINT="$ENDPOINT"
export NEPTUNE_READER_ENDPOINT="$READER_ENDPOINT"
export NEPTUNE_PORT="$PORT"
export NEPTUNE_REGION="$REGION"
export NEPTUNE_SECURITY_GROUP="$SG_ID"
EOF

echo -e "${GREEN}✓ Configuration saved to: $CONFIG_FILE${NC}"
echo ""
echo "Load configuration:"
echo "  source $CONFIG_FILE"

###############################################################################
# FINAL SUMMARY
###############################################################################

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    SETUP COMPLETE!                             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Neptune Endpoint: $ENDPOINT${NC}"
echo ""
echo "Next Steps:"
echo ""
echo "1. Enable Bedrock Titan access:"
echo "   • Go to: https://console.aws.amazon.com/bedrock"
echo "   • Request: amazon.titan-embed-text-v1"
echo ""
echo "2. Run the load job:"
echo "   cd /Users/hcherian/Documents/Claude-data-operations"
echo ""
echo "   python shared/semantic_layer/load_to_neptune.py \\"
echo "     --workload financial_portfolios \\"
echo "     --database financial_portfolios_db \\"
echo "     --neptune-endpoint $ENDPOINT \\"
echo "     --region $REGION"
echo ""
echo "3. Verify setup:"
echo "   python shared/semantic_layer/verify_setup.py \\"
echo "     --workload financial_portfolios \\"
echo "     --database financial_portfolios_db \\"
echo "     --neptune-endpoint $ENDPOINT \\"
echo "     --verbose"
echo ""
echo -e "${YELLOW}Cost: ~\$0.12/hour (db.t3.medium)${NC}"
echo ""
echo "To delete cluster later:"
echo "  bash shared/semantic_layer/delete_neptune.sh"
echo ""
