# MCP-Based PII Tagging Solution

**Created:** March 17, 2026
**Status:** ✅ SOLUTION DESIGNED

---

## Current MCP Server Status

### Working MCP Servers (Loaded)

| Server | Status | Available Tools |
|--------|--------|-----------------|
| **iam** | ✅ Loaded | User/Role/Policy management |
| **lambda** | ✅ Loaded | Lambda function invocation |
| **redshift** | ✅ Loaded | Query execution |
| **cloudtrail** | ✅ Loaded | Event lookup |

### Not Loaded MCP Servers

| Server | Status | Reason |
|--------|--------|--------|
| **lakeformation** | ❌ Not Loaded | Connection failed during setup |
| **s3-tables** | ❌ Not Loaded | Connection failed |
| **sagemaker-catalog** | ❌ Not Loaded | Connection failed |
| Others (12 total) | ❌ Not Loaded | Various connection issues |

---

## Solution Options

### Option 1: Lambda MCP-Based Solution (Recommended)

**Approach:** Create a Lambda function for PII tagging, invoke via `lambda` MCP server

**Advantages:**
- ✅ Uses working MCP server (`lambda`)
- ✅ Scalable and serverless
- ✅ Can be called from Claude Code via MCP
- ✅ Event-driven (can trigger on S3 uploads)
- ✅ Centralized governance function

**Implementation:**

```python
# Lambda function: pii-detection-and-tagging
import json
import boto3
import re
from typing import Dict, List

glue = boto3.client('glue')
athena = boto3.client('athena')
lakeformation = boto3.client('lakeformation')

def lambda_handler(event, context):
    """
    Lambda function for PII detection and tagging.

    Event structure:
    {
      "database": "finsights_silver",
      "table": "funds_clean",  # or "all_tables": true
      "content_detection": true,
      "apply_tags": true
    }
    """
    database = event.get('database')
    table = event.get('table')
    all_tables = event.get('all_tables', False)
    content_detection = event.get('content_detection', True)
    apply_tags = event.get('apply_tags', True)

    # Ensure LF-Tags exist
    ensure_lf_tags()

    # Get tables to scan
    tables_to_scan = []
    if all_tables:
        response = glue.get_tables(DatabaseName=database)
        tables_to_scan = [t['Name'] for t in response['TableList']]
    else:
        tables_to_scan = [table]

    # Scan each table
    results = {}
    for table_name in tables_to_scan:
        pii_results = scan_table_for_pii(
            database,
            table_name,
            content_detection
        )

        if pii_results and apply_tags:
            apply_lf_tags_to_columns(database, table_name, pii_results)

        results[table_name] = pii_results

    return {
        'statusCode': 200,
        'body': json.dumps({
            'database': database,
            'tables_scanned': len(tables_to_scan),
            'tables_with_pii': len([r for r in results.values() if r]),
            'results': results
        })
    }

# ... (include PII detection logic from pii_detection_and_tagging.py)
```

**Deployment:**

```bash
# 1. Package Lambda function
cd scripts/governance/
zip -r pii-lambda.zip pii_detection_and_tagging.py

# 2. Create Lambda function
aws lambda create-function \
  --function-name pii-detection-and-tagging \
  --runtime python3.11 \
  --role arn:aws:iam::123456789012:role/LambdaLakeFormationRole \
  --handler pii_detection_and_tagging.lambda_handler \
  --zip-file fileb://pii-lambda.zip \
  --timeout 900 \
  --memory-size 512 \
  --environment "Variables={SAMPLE_SIZE=100}"

# 3. Test via MCP (from Claude Code)
# Use mcp__lambda__pii-detection-and-tagging tool
```

**Usage from Claude Code:**

```
Invoke the pii-detection-and-tagging Lambda function to scan finsights_silver database for all tables.
```

Claude Code would use:
```python
mcp__lambda__['pii-detection-and-tagging'](
    event={
        'database': 'finsights_silver',
        'all_tables': True,
        'content_detection': True,
        'apply_tags': True
    }
)
```

---

### Option 2: Direct Lake Formation MCP Integration (Requires Fix)

**Approach:** Fix the lakeformation MCP server connection

**Challenges:**
- ❌ Current server connection failed
- ❌ May require MCP server update/reconfiguration
- ❌ Not immediately available

**If Fixed, Would Enable:**
- Direct LF-Tag creation
- Direct tag assignment to resources
- Tag-based policy queries

**Deferred:** Not recommended as immediate solution

---

### Option 3: Hybrid Approach (Current Implementation)

**Approach:** Python script + AWS CLI (boto3)

**Current Status:** ✅ Already Implemented

**Script:** `scripts/governance/pii_detection_and_tagging.py`

**Advantages:**
- ✅ Works immediately
- ✅ No MCP dependency
- ✅ Full feature set
- ✅ Can be called from anywhere

**Usage:**
```bash
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_silver \
  --all-tables
```

---

## Recommended Implementation Path

### Phase 1: Current (Hybrid) ✅ COMPLETE

Use Python script with boto3:
- Script location: `scripts/governance/pii_detection_and_tagging.py`
- Documentation: `PII_DETECTION_AND_TAGGING.md`
- Status: Fully functional

### Phase 2: Lambda + MCP Integration (Optional Enhancement)

**Step 1: Create Lambda-based PII Tagger**

```bash
# Create Lambda function from existing script
scripts/governance/create_pii_lambda.sh
```

**Step 2: Test Lambda Invocation**

```bash
aws lambda invoke \
  --function-name pii-detection-and-tagging \
  --payload '{"database":"finsights_silver","all_tables":true}' \
  /tmp/response.json
```

**Step 3: Use via MCP**

From Claude Code:
```
Use the lambda MCP to invoke pii-detection-and-tagging for database finsights_gold
```

### Phase 3: Event-Driven Automation (Future)

**Trigger PII tagging automatically:**

```bash
# S3 Event → Lambda → PII Detection → LF-Tags
aws s3api put-bucket-notification-configuration \
  --bucket your-datalake-bucket \
  --notification-configuration '{
    "LambdaFunctionConfigurations": [{
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:pii-detection-and-tagging",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {"FilterRules": [{"Name": "prefix", "Value": "silver/"}]}
      }
    }]
  }'
```

**Result:** Automatic PII tagging whenever new data lands in Silver zone

---

## Creating the Lambda Function

### Step 1: Prepare Lambda Package

```bash
cd /path/to/claude-data-operations/workloads/us_mutual_funds_etf

# Create Lambda package directory
mkdir -p lambda/pii-tagger
cp scripts/governance/pii_detection_and_tagging.py lambda/pii-tagger/

# Modify for Lambda (add lambda_handler)
cat >> lambda/pii-tagger/pii_detection_and_tagging.py << 'EOF'

# Lambda handler
def lambda_handler(event, context):
    """
    Lambda handler for PII detection and tagging.

    Event structure:
    {
      "database": "finsights_silver",
      "table": "funds_clean",
      "all_tables": false,
      "content_detection": true,
      "apply_tags": true
    }
    """
    import sys
    from io import StringIO

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()

    try:
        # Parse event
        database = event.get('database')
        table = event.get('table')
        all_tables = event.get('all_tables', False)
        content_detection = event.get('content_detection', True)
        apply_tags = event.get('apply_tags', True)

        # Ensure LF-Tags exist
        ensure_lf_tags_exist()

        # Get tables to scan
        tables_to_scan = []
        if all_tables:
            try:
                response = glue.get_tables(DatabaseName=database)
                tables_to_scan = [table['Name'] for table in response['TableList']]
            except Exception as e:
                logger.error(f"Error listing tables: {e}")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': str(e)})
                }
        else:
            if not table:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Must specify table or all_tables=true'})
                }
            tables_to_scan = [table]

        # Scan each table
        all_results = {}
        for table_name in tables_to_scan:
            try:
                pii_results = scan_table_for_pii(
                    database,
                    table_name,
                    content_detection=content_detection
                )

                if pii_results and apply_tags:
                    apply_lf_tags_to_columns(database, table_name, pii_results)

                all_results[table_name] = pii_results

            except Exception as e:
                logger.error(f"Error processing table {table_name}: {e}")
                all_results[table_name] = {'error': str(e)}

        # Calculate summary
        total_pii_columns = sum(len(results) for results in all_results.values() if isinstance(results, dict) and 'error' not in results)
        tables_with_pii = sum(1 for results in all_results.values() if isinstance(results, dict) and results and 'error' not in results)

        # Restore stdout
        sys.stdout = old_stdout
        output = captured_output.getvalue()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'PII detection completed',
                'database': database,
                'tables_scanned': len(tables_to_scan),
                'tables_with_pii': tables_with_pii,
                'total_pii_columns': total_pii_columns,
                'results': all_results,
                'logs': output[-1000:]  # Last 1000 chars of logs
            }, indent=2)
        }

    except Exception as e:
        sys.stdout = old_stdout
        logger.error(f"Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

EOF

# Package Lambda
cd lambda/pii-tagger
zip -r ../pii-tagger.zip .
cd ../..
```

### Step 2: Create IAM Role for Lambda

```bash
# Create trust policy
cat > /tmp/lambda-trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

# Create role
aws iam create-role \
  --role-name LambdaPIITaggerRole \
  --assume-role-policy-document file:///tmp/lambda-trust-policy.json

# Attach policies
aws iam attach-role-policy \
  --role-name LambdaPIITaggerRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam attach-role-policy \
  --role-name LambdaPIITaggerRole \
  --policy-arn arn:aws:iam::aws:policy/AWSGlueConsoleFullAccess

aws iam attach-role-policy \
  --role-name LambdaPIITaggerRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonAthenaFullAccess

# Create inline policy for Lake Formation
cat > /tmp/lf-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lakeformation:CreateLFTag",
        "lakeformation:GetLFTag",
        "lakeformation:AddLFTagsToResource",
        "lakeformation:RemoveLFTagsFromResource",
        "lakeformation:GetResourceLFTags",
        "lakeformation:ListLFTags"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name LambdaPIITaggerRole \
  --policy-name LakeFormationTagging \
  --policy-document file:///tmp/lf-policy.json
```

### Step 3: Deploy Lambda Function

```bash
aws lambda create-function \
  --function-name pii-detection-and-tagging \
  --runtime python3.11 \
  --role arn:aws:iam::123456789012:role/LambdaPIITaggerRole \
  --handler pii_detection_and_tagging.lambda_handler \
  --zip-file fileb://lambda/pii-tagger.zip \
  --timeout 900 \
  --memory-size 1024 \
  --environment "Variables={SAMPLE_SIZE=100,ATHENA_OUTPUT_BUCKET=s3://your-datalake-bucket/athena-results/}" \
  --region us-east-1
```

### Step 4: Test Lambda Function

```bash
# Test with single table
aws lambda invoke \
  --function-name pii-detection-and-tagging \
  --payload '{"database":"finsights_silver","table":"funds_clean","content_detection":true,"apply_tags":true}' \
  /tmp/pii-response.json

# View results
cat /tmp/pii-response.json | jq '.'

# Test with all tables
aws lambda invoke \
  --function-name pii-detection-and-tagging \
  --payload '{"database":"finsights_gold","all_tables":true,"content_detection":false,"apply_tags":true}' \
  /tmp/pii-response-all.json
```

---

## Using Lambda via MCP from Claude Code

Once Lambda is deployed, you can invoke it from Claude Code using the `lambda` MCP server:

**Example prompts:**

```
Use the lambda MCP to invoke pii-detection-and-tagging function for database finsights_silver, scanning all tables with content detection enabled.
```

```
Invoke the PII tagging Lambda for table customer_data in finsights_gold database.
```

```
Run PII detection via Lambda on finsights_silver.orders table without applying tags (detect only).
```

Claude Code will translate this to:
```python
mcp__lambda__['pii-detection-and-tagging'](
    event={
        'database': 'finsights_silver',
        'all_tables': True,
        'content_detection': True,
        'apply_tags': True
    }
)
```

---

## Comparison of Approaches

| Feature | Python Script | Lambda + MCP | Native LF MCP |
|---------|--------------|--------------|---------------|
| **Availability** | ✅ Now | ⏸️ Setup Required | ❌ Not Working |
| **Ease of Use** | ✅ Simple | ✅ Simple | ✅ Would be simplest |
| **Scalability** | ⚠️  Manual | ✅ Automatic | ✅ Automatic |
| **Event-Driven** | ❌ No | ✅ Yes | ✅ Yes |
| **Cost** | Free | ~$0.01/run | Free |
| **MCP Integration** | ❌ No | ✅ Yes | ✅ Yes |
| **Maintenance** | Low | Medium | Low |

---

## Recommendation

**Immediate Use:** Python script (`pii_detection_and_tagging.py`) ✅

**Future Enhancement:** Lambda + MCP integration ⏸️

**Long-term:** Native Lake Formation MCP (if/when connection fixed) 🔮

---

**Document Created:** March 17, 2026 @ 6:30 AM EST
**Status:** Solution designed, Python script already working
**Next Action:** Optional Lambda deployment for MCP integration
