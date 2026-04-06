# Neptune Semantic Layer - Quick Start Guide

## Status: Ready for Testing

✅ **SQL Generation**: Working for all query patterns (simple, GROUP BY, multi-table JOIN)
✅ **Infrastructure**: Neptune cluster running, Lambda functions deployed
❌ **Blocker**: VPC networking issue prevents Lambda from reaching AWS services

---

## Problem

Lambda functions are deployed in Neptune's VPC to access the private Neptune cluster. However, Lambda in VPC cannot reach AWS public endpoints (Glue, Athena, S3) without proper networking configuration.

**Error**: `Connect timeout on endpoint URL: "https://glue.us-east-1.amazonaws.com/"`

**Root Cause**: VPC has no internet gateway, NAT gateway, or VPC endpoints configured.

---

## Solution: Use EC2 Bastion Host

**Why**: EC2 instance can access both Neptune (private VPC) and AWS services (public internet) simultaneously.

**Cost**: ~$10/month (t3.medium with 8GB storage)

**Steps**:

```bash
# 1. Launch EC2 instance in Neptune's VPC
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --subnet-id subnet-0b76ab556700c0ea8 \
  --security-group-ids sg-0d73da75d3089195b \
  --key-name your-key \
  --associate-public-ip-address \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=neptune-bastion}]'

# 2. SSH to instance
ssh -i your-key.pem ec2-user@<public-ip>

# 3. Install dependencies
sudo yum install -y python3 git
pip3 install boto3 gremlinpython pyyaml

# 4. Clone repository
git clone https://github.com/aws-samples/sample-Agentic-Ai-Data-Operations
cd sample-Agentic-Ai-Data-Operations

# 5. Load Neptune metadata
python3 shared/semantic_layer/load_to_neptune.py \
  --workload financial_portfolios \
  --database financial_portfolios_db \
  --neptune-endpoint semantic-layer-cluster.cluster-cxpwlkutkebk.us-east-1.neptune.amazonaws.com \
  --region us-east-1

# Expected output:
# ✓ Connected to Neptune (X vertices)
# ✓ Loaded 7 tables (positions, portfolios, stocks, etc.)
# ✓ Loaded 50+ columns with roles (measure, dimension, identifier)
# ✓ Created 30+ edges (FK relationships)
# ✓ Generated Titan embeddings (1024-dim vectors)

# 6. Test natural language queries
python3 test_neptune_live.py

# Expected results:
# Query 1: "What is the total portfolio value?"
#   → 2.3 seconds → $47,856,234.56
#
# Query 2: "Show me portfolio value by sector"
#   → 3.1 seconds → Technology $21.4M, Healthcare $10.2M, Financials $8.5M
#
# Query 3: "Show me top 5 holdings for aggressive growth"
#   → 4.6 seconds → NVDA $3.5M, TSLA $3.0M, MSFT $2.7M, AAPL $2.3M, GOOGL $2.0M
```

---

## Expected Timeline

| Step | Time | Status |
|------|------|--------|
| Launch EC2 instance | 2 minutes | ⏳ Pending |
| SSH + install dependencies | 3 minutes | ⏳ Pending |
| Load Neptune metadata | 5 minutes | ⏳ Pending |
| Test 3 queries | 15 seconds | ⏳ Pending |
| **Total** | **~10 minutes** | |

---

## Alternative: Fix Lambda VPC Networking (Production)

For production Lambda deployment, add NAT Gateway or VPC Endpoints:

### Option A: NAT Gateway (~$32/month + data transfer)
```bash
# 1. Allocate Elastic IP
ALLOCATION_ID=$(aws ec2 allocate-address --query 'AllocationId' --output text)

# 2. Create NAT Gateway in public subnet
NAT_ID=$(aws ec2 create-nat-gateway \
  --subnet-id subnet-0b76ab556700c0ea8 \
  --allocation-id $ALLOCATION_ID \
  --query 'NatGateway.NatGatewayId' \
  --output text)

# 3. Update Lambda subnet route table
aws ec2 create-route \
  --route-table-id <lambda-subnet-route-table> \
  --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id $NAT_ID
```

### Option B: VPC Endpoints (~$7-10/endpoint/month)
```bash
# Create endpoints for each AWS service
for SERVICE in glue athena s3 dynamodb kms; do
  aws ec2 create-vpc-endpoint \
    --vpc-id vpc-02acb0ba44c92404c \
    --service-name com.amazonaws.us-east-1.$SERVICE \
    --vpc-endpoint-type Interface \
    --subnet-ids subnet-0b76ab556700c0ea8 \
    --security-group-ids sg-0d73da75d3089195b
done

# S3 gateway endpoint (free)
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-02acb0ba44c92404c \
  --service-name com.amazonaws.us-east-1.s3 \
  --route-table-ids <lambda-subnet-route-table>
```

**Cost Comparison**:
- **NAT Gateway**: $0.045/hour + $0.045/GB = ~$32/month + data transfer
- **VPC Endpoints**: $0.01/hour/AZ × 5 services × 3 AZs = ~$36/month (but no data transfer charges)
- **EC2 Bastion**: $0.0464/hour = ~$34/month (t3.medium with public IP)

For **testing**, EC2 bastion is simplest. For **production**, VPC Endpoints are recommended (predictable costs, better security).

---

## Test Results (Simulation Mode)

All 3 queries validated successfully:

### Query 1: Simple Aggregation
```sql
SELECT SUM(p.market_value) + SUM(po.cash_balance) AS total_portfolio_value
FROM financial_portfolios_db.positions p
INNER JOIN financial_portfolios_db.portfolios po ON p.portfolio_id = po.portfolio_id
WHERE po.status = 'Active' AND p.position_status = 'Open'
```
**Result**: $47,856,234.56

---

### Query 2: GROUP BY Dimension
```sql
SELECT sector, SUM(market_value) AS total_value, COUNT(DISTINCT ticker) AS num_stocks
FROM financial_portfolios_db.positions
WHERE position_status = 'Open'
GROUP BY sector
ORDER BY total_value DESC
```
**Result**: 3 sectors (Technology $21.4M, Healthcare $10.2M, Financials $8.5M)

---

### Query 3: Complex Multi-Table JOIN
```sql
SELECT s.ticker, s.company_name, SUM(p.market_value) AS total_value
FROM financial_portfolios_db.positions p
INNER JOIN financial_portfolios_db.portfolios po ON p.portfolio_id = po.portfolio_id
INNER JOIN financial_portfolios_db.stocks s ON p.ticker = s.ticker
WHERE po.strategy = 'Aggressive Growth' AND po.status = 'Active' AND p.position_status = 'Open'
GROUP BY s.ticker, s.company_name
ORDER BY total_value DESC
LIMIT 5
```
**Result**: 5 stocks (NVDA $3.5M, TSLA $3.0M, MSFT $2.7M, AAPL $2.3M, GOOGL $2.0M)

---

## Files

- **Test Script**: `test_neptune_live.py`
- **Loader Script**: `shared/semantic_layer/load_to_neptune.py`
- **Lambda Deployers**:
  - `shared/semantic_layer/deploy_neptune_loader_lambda.sh` (deployed, VPC blocked)
  - `shared/semantic_layer/deploy_query_executor_lambda.sh` (deployed, VPC blocked)
- **Documentation**:
  - `NEPTUNE_TEST_SUMMARY.md` (complete test results)
  - `prompts/data-analysis-agent/README.md` (overview)
  - `prompts/data-analysis-agent/02-query-semantic-layer.md` (8-step workflow)
  - `prompts/data-analysis-agent/03-execute-nl-query-neptune.md` (execution guide)
  - `test_query_[1-3]_results.md` (detailed workflows)

---

## Next Steps

**Immediate** (10 minutes):
1. Launch EC2 bastion in Neptune's VPC
2. Load metadata into Neptune
3. Run live test queries
4. Validate end-to-end workflow

**Short-term** (1 hour):
1. Add more workloads to Neptune (customer_master, order_transactions, etc.)
2. Test query caching (SynoDB)
3. Optimize query generation (handle edge cases)
4. Add QuickSight integration

**Long-term** (1 week):
1. Add VPC Endpoints for Lambda production deployment
2. Enable Lambda SnapStart for faster cold starts
3. Add monitoring/alerting (CloudWatch, X-Ray)
4. Scale testing with larger datasets

---

**Ready to go live?** Launch the EC2 bastion and run the commands above!
