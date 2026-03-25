#!/bin/bash

###############################################################################
# Neptune Cluster Deletion Script
# Safely deletes Neptune cluster and related resources
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
CLUSTER_ID="${CLUSTER_ID:-semantic-layer-cluster}"
REGION="${AWS_REGION:-us-east-1}"

# Load configuration if exists
CONFIG_FILE="shared/semantic_layer/neptune_config.sh"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
    CLUSTER_ID="${NEPTUNE_CLUSTER_ID:-$CLUSTER_ID}"
    REGION="${NEPTUNE_REGION:-$REGION}"
fi

echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║           Neptune Cluster Deletion (DANGEROUS!)                ║${NC}"
echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}⚠️  WARNING: This will permanently delete:${NC}"
echo "  • Neptune cluster: $CLUSTER_ID"
echo "  • All instances in the cluster"
echo "  • All graph data"
echo "  • Automated backups"
echo ""
echo -e "${RED}This action CANNOT be undone!${NC}"
echo ""
read -p "Type 'DELETE' to confirm: " confirm

if [ "$confirm" != "DELETE" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Deleting Neptune cluster..."

# Get all instances in cluster
echo "Finding instances..."
INSTANCES=$(aws neptune describe-db-instances \
    --region "$REGION" \
    --query "DBInstances[?DBClusterIdentifier=='$CLUSTER_ID'].DBInstanceIdentifier" \
    --output text)

if [ ! -z "$INSTANCES" ]; then
    # Delete instances
    for instance in $INSTANCES; do
        echo "Deleting instance: $instance"
        aws neptune delete-db-instance \
            --db-instance-identifier "$instance" \
            --region "$REGION" \
            --skip-final-snapshot
    done

    echo "Waiting for instances to be deleted (2 minutes)..."
    sleep 120
fi

# Delete cluster
echo "Deleting cluster: $CLUSTER_ID"
aws neptune delete-db-cluster \
    --db-cluster-identifier "$CLUSTER_ID" \
    --region "$REGION" \
    --skip-final-snapshot

echo "Waiting for cluster to be deleted (1 minute)..."
sleep 60

echo -e "${GREEN}✓ Cluster deletion initiated${NC}"
echo ""
echo "Cluster will be fully deleted in 5-10 minutes."
echo ""
echo "To verify deletion:"
echo "  aws neptune describe-db-clusters --db-cluster-identifier $CLUSTER_ID --region $REGION"
echo ""
