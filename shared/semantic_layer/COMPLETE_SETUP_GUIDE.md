# Complete Setup Guide - Neptune + Semantic Layer

**Everything you need to go from zero to querying with natural language.**

---

## 🎯 Quick Overview

You'll run **3 commands total**:

1. **Create Neptune cluster** (~10 minutes, one-time)
2. **Load metadata** (~40 seconds)
3. **Query with natural language** (instant)

**Total cost**: ~$0.22 + $0.12/hour for Neptune

---

## 📋 Prerequisites

Before starting, ensure you have:

- [ ] AWS CLI installed (`aws --version`)
- [ ] AWS credentials configured (`aws sts get-caller-identity`)
- [ ] Python 3.8+ installed
- [ ] Dependencies installed: `pip install boto3 gremlinpython pyyaml`
- [ ] You're in the project directory: `/Users/hcherian/Documents/Claude-data-operations`

---

## 🚀 Step 1: Create Neptune Cluster (10 minutes)

### Run the Setup Script

```bash
cd /Users/hcherian/Documents/Claude-data-operations

bash shared/semantic_layer/setup_neptune.sh
```

### What This Does

The script will:

1. ✅ Check AWS credentials
2. ✅ Find your VPC and subnets
3. ✅ Create security group (port 8182)
4. ✅ Create Neptune cluster
5. ✅ Create Neptune instance (db.t3.medium)
6. ✅ Test connection
7. ✅ Save configuration to `neptune_config.sh`

### Expected Output

```
╔════════════════════════════════════════════════════════════════╗
║                    SETUP COMPLETE!                             ║
╚════════════════════════════════════════════════════════════════╝

Neptune Endpoint: semantic-layer-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com

Next Steps:

1. Enable Bedrock Titan access
2. Run the load job
3. Verify setup
```

### Save the Endpoint!

**IMPORTANT**: Copy the Neptune endpoint from the output. You'll need it for the next steps.

Example endpoint:
```
semantic-layer-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com
```

---

## ⚡ Step 2: Enable Bedrock Titan (1 minute)

### Option A: AWS Console (Easiest)

1. Go to: https://console.aws.amazon.com/bedrock
2. Click: **Model access** (left sidebar)
3. Click: **Request model access**
4. Find: **Titan Embeddings G1 - Text**
5. Check the box
6. Click: **Request model access**
7. Wait for approval (usually instant)

### Option B: AWS CLI

```bash
# Check if you have access
aws bedrock list-foundation-models \
  --by-provider amazon \
  --query 'modelSummaries[?contains(modelId, `titan-embed`)].modelId'

# Test access
aws bedrock-runtime invoke-model \
  --model-id amazon.titan-embed-text-v1 \
  --body '{"inputText":"test"}' \
  /tmp/output.json

cat /tmp/output.json | jq '.embedding | length'
# Should output: 1024
```

---

## 📊 Step 3: Load Metadata into Neptune (40 seconds)

### Run the Load Script

```bash
# Replace YOUR-NEPTUNE-ENDPOINT with the endpoint from Step 1
python shared/semantic_layer/load_to_neptune.py \
  --workload financial_portfolios \
  --database financial_portfolios_db \
  --neptune-endpoint YOUR-NEPTUNE-ENDPOINT.amazonaws.com \
  --region us-east-1
```

**Example with real endpoint:**
```bash
python shared/semantic_layer/load_to_neptune.py \
  --workload financial_portfolios \
  --database financial_portfolios_db \
  --neptune-endpoint semantic-layer-cluster.cluster-xyz.us-east-1.neptune.amazonaws.com \
  --region us-east-1
```

### What This Does (7 Steps)

```
STEP 1: Read semantic.yaml                  ✓ (0.1s)
STEP 2: Fetch Glue Catalog metadata         ✓ (2.5s)
STEP 3: Fetch Lake Formation LF-Tags        ✓ (1.2s)
STEP 4: Generate Titan embeddings           ✓ (18s)
STEP 5: Load graph into Neptune             ✓ (12s)
STEP 6: Create DynamoDB table               ✓ (1.5s)
STEP 7: Load seed queries                   ✓ (3.2s)
                                            ─────────
Total:                                      ~40 seconds
```

### Expected Output

```
================================================================================
LOADING COMPLETE!
================================================================================
Workload:             financial_portfolios
Database:             financial_portfolios_db
────────────────────────────────────────────────────────────────────────────────
Tables:               3
Columns:              23
Relationships:        3
Business Terms:       8
────────────────────────────────────────────────────────────────────────────────
Embeddings Generated: 50
Neptune Vertices:     ~40
Neptune Edges:        ~35
Seed Queries:         8
================================================================================

✓ Semantic layer is ready!
```

---

## ✅ Step 4: Verify Setup (30 seconds)

```bash
python shared/semantic_layer/verify_setup.py \
  --workload financial_portfolios \
  --database financial_portfolios_db \
  --neptune-endpoint YOUR-NEPTUNE-ENDPOINT \
  --verbose
```

### Expected Output

```
================================================================================
SEMANTIC LAYER VERIFICATION
================================================================================
✓ PASS   Semantic YAML            semantic.yaml found (3 tables)
✓ PASS   Glue Catalog              Glue database found (3 tables)
✓ PASS   Lake Formation            Lake Formation LF-Tags configured
✓ PASS   Bedrock Titan             Bedrock Titan embeddings accessible
✓ PASS   Neptune Connection        Neptune cluster accessible (40 vertices)
✓ PASS   Neptune Graph             Graph loaded (3 tables, 23 columns)
✓ PASS   SynoDB Table              SynoDB table active (8 queries)
✓ PASS   SynoDB Queries            Seed queries loaded
================================================================================
Results: 8 passed, 0 failed (total: 8)
================================================================================

✓ All checks passed! Semantic layer is ready.
```

---

## 🎉 Step 5: Query with Natural Language!

### Python API

```python
from shared.semantic_layer import execute_nl_query

# Ask a natural language question
gen_result, exec_result = execute_nl_query(
    nl_query="What is the total portfolio value by region?",
    workload="financial_portfolios",
    database="financial_portfolios_db",
    neptune_endpoint="YOUR-NEPTUNE-ENDPOINT",
    athena_database="financial_portfolios_db",
    s3_output_location="s3://your-bucket/athena-results/"
)

# See generated SQL
print("Generated SQL:")
print(gen_result.sql)
print()

# See results
print("Results:")
for row in exec_result.rows:
    print(row)
```

### Expected Output

```
Generated SQL:
SELECT
  portfolios.region,
  SUM(positions.market_value) AS total_value
FROM financial_portfolios_db.positions
JOIN financial_portfolios_db.portfolios
  ON positions.portfolio_id = portfolios.portfolio_id
GROUP BY portfolios.region
ORDER BY total_value DESC
LIMIT 10000

Results:
{'region': 'North America', 'total_value': '5234567.89'}
{'region': 'Europe', 'total_value': '3456789.12'}
{'region': 'Asia Pacific', 'total_value': '2345678.90'}
```

---

## 🔍 What You Just Created

### In Neptune

**40 vertices** with embeddings:
```
1 Database (financial_portfolios_db)
├─ 3 Tables (portfolios, positions, stocks)
│  Each with: embedding (1024 dims), type, grain
│
├─ 23 Columns (portfolio_id, market_value, region, ...)
│  Each with: embedding (1024 dims), role, aggregation, PII tags
│
└─ 8 Business Terms (Market Value, AUM, ...)
   Each with: embedding (1024 dims), synonyms
```

**35 edges** (relationships):
```
Database ──contains──> Tables (3)
Tables ──has_column──> Columns (23)
Columns ──references──> Columns (3 FKs)
Columns ──described_by──> Business Terms (15)
```

### In DynamoDB (SynoDB)

**8 seed queries** with embeddings:
```
• "What is the total portfolio value?"
• "Show me top 10 holdings by market value"
• "What is the average portfolio return?"
• ... (5 more)
```

### Total Storage

- Neptune: ~500 KB graph data + ~200 KB embeddings
- DynamoDB: ~50 KB seed queries

---

## 💰 Cost Breakdown

| Item | Cost | Frequency |
|------|------|-----------|
| Neptune cluster (db.t3.medium) | $0.12/hour | Ongoing |
| Titan embeddings (50 calls) | $0.10 | One-time |
| DynamoDB (free tier) | $0.00 | Ongoing |
| **First hour** | **$0.22** | - |
| **Per day (24 hours)** | **$2.88** | - |
| **Per month** | **~$87** | - |

**Note**: Stop Neptune cluster when not in use to save costs!

---

## 🎯 Example Queries to Try

Once setup is complete, try these:

```python
from shared.semantic_layer import execute_nl_query

# 1. Simple aggregation
execute_nl_query("What is the total portfolio value?", ...)

# 2. Group by dimension
execute_nl_query("Show me revenue by region", ...)

# 3. Time series
execute_nl_query("What is the monthly trend in AUM?", ...)

# 4. Filtering
execute_nl_query("Show me portfolios with value > $1M", ...)

# 5. Ranking
execute_nl_query("Who are the top 10 customers by assets?", ...)

# 6. Comparison
execute_nl_query("Compare this month vs last month", ...)

# 7. Join across tables
execute_nl_query("Show me customer names with their portfolio values", ...)
```

---

## 🔧 Troubleshooting

### Error: "Neptune connection refused"

**Fix:**
```bash
# Check endpoint
aws neptune describe-db-clusters \
  --db-cluster-identifier semantic-layer-cluster \
  --region us-east-1

# Check security group
aws ec2 describe-security-groups \
  --group-ids YOUR-SG-ID
```

### Error: "Bedrock access denied"

**Fix:**
```bash
# Check model access
aws bedrock list-foundation-models \
  --by-provider amazon

# If not approved, go to console:
# https://console.aws.amazon.com/bedrock
```

### Error: "Glue database not found"

**Fix:**
```bash
# Check database exists
aws glue get-database --name financial_portfolios_db

# If not, create it first
aws glue create-database \
  --database-input '{"Name":"financial_portfolios_db"}'
```

---

## 🛑 How to Stop/Delete (Save Costs)

### Option 1: Stop Cluster (Temporary)

```bash
# Stop instance (stops billing)
aws neptune stop-db-cluster \
  --db-cluster-identifier semantic-layer-cluster \
  --region us-east-1

# Start again later
aws neptune start-db-cluster \
  --db-cluster-identifier semantic-layer-cluster \
  --region us-east-1
```

### Option 2: Delete Cluster (Permanent)

```bash
bash shared/semantic_layer/delete_neptune.sh
```

**WARNING**: This permanently deletes all data!

---

## 📖 Next Steps

After setup is complete:

1. ✅ **Try example queries** - Test the semantic layer
2. ⏭️ **Add more workloads** - Run load script for other datasets
3. ⏭️ **Create MCP server** - Expose via Model Context Protocol
4. ⏭️ **Build UI** - Add web interface for queries
5. ⏭️ **Monitor usage** - Track query patterns and costs

---

## 📚 Additional Resources

| Document | Purpose |
|----------|---------|
| **RUN_LOAD_JOB.md** | Detailed load job instructions |
| **KNOWLEDGE_GRAPH_EXPLAINED.md** | How YAML → Graph works |
| **QUICK_REFERENCE.txt** | One-page cheat sheet |
| **README.md** | Full API reference |

All in: `shared/semantic_layer/`

---

## ✅ Success Checklist

After completing this guide, you should have:

- [ ] Neptune cluster running
- [ ] Bedrock Titan access enabled
- [ ] Metadata loaded (40 vertices, 35 edges)
- [ ] Embeddings generated (50 total)
- [ ] SynoDB queries loaded (8 seed queries)
- [ ] Verification passed (8/8 checks)
- [ ] Natural language queries working

---

**Total Time**: ~15 minutes (10 min setup + 5 min loading/verification)

**Total Cost**: $0.22 one-time + $0.12/hour ongoing

**Result**: Complete semantic layer for NL → SQL! 🎉

---

Need help? See `shared/semantic_layer/START_HERE.md`
