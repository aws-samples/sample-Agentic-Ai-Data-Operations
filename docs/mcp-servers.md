# MCP Server Architecture for Data Onboarding

This document maps every tool and operation in the Agentic Data Onboarding System to Model Context Protocol (MCP) servers, ensuring all AWS interactions go through standardized, auditable MCP interfaces.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   Data Onboarding Agent                         │
│                  (orchestrates via MCP calls)                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ All operations via MCP
                         │
        ┌────────────────┴────────────────┐
        │                                  │
        ▼                                  ▼
┌─────────────────┐              ┌─────────────────┐
│  AWS MCP Servers │              │ Local MCP Servers│
│  (awslabs/mcp)   │              │  (custom)        │
└─────────────────┘              └─────────────────┘
        │                                  │
        │                                  │
        ▼                                  ▼
┌─────────────────────────────────────────────────┐
│            AWS Services                         │
│  Glue • Athena • S3 • DynamoDB • SageMaker     │
│  Step Functions • Lambda • OpenSearch • KMS     │
└─────────────────────────────────────────────────┘
```

## MCP Server Mapping

### 1. Data Processing & Cataloging (Phase 3: Profiling & Discovery)

| Operation | MCP Server | Tool/Method | Priority |
|-----------|------------|-------------|----------|
| **Glue Crawler** - Schema discovery | `aws-dataprocessing-mcp-server` | `create_crawler`, `start_crawler`, `get_crawler` | PRIMARY |
| **Athena Query** - 5% profiling | `aws-dataprocessing-mcp-server` | `start_query_execution`, `get_query_results` | PRIMARY |
| **Glue Data Catalog** - Read schema | `aws-dataprocessing-mcp-server` | `get_database`, `get_table`, `get_partitions` | PRIMARY |
| **SageMaker Catalog** - Business metadata | LOCAL: `sagemaker-catalog-mcp-server` | `put_custom_metadata`, `get_custom_metadata` | CUSTOM |

**AWS DataProcessing MCP Server** covers:
- AWS Glue (Crawlers, Data Catalog, ETL Jobs, Interactive Sessions, Workflows)
- Amazon EMR-EC2 (Cluster Management, Steps)
- Amazon Athena (Query Execution, Named Queries, Data Catalogs, Workgroups)

### 2. Bronze Zone (Phase 4: Ingestion)

| Operation | MCP Server | Tool/Method | Priority |
|-----------|------------|-------------|----------|
| **S3 Copy/Sync** - Raw ingestion | `core-mcp-server` (AWS SDK) | `s3.copy_object`, `s3.put_object` | PRIMARY |
| **Glue ETL Job** - DB→S3 extract | `aws-dataprocessing-mcp-server` | `create_job`, `start_job_run` | PRIMARY |
| **Lambda** - API→S3 ingestion | `lambda-tool-mcp-server` | `invoke_function` | PRIMARY |
| **S3 Object Lock** - Immutability | `core-mcp-server` (AWS SDK) | `s3.put_object_lock_configuration` | PRIMARY |

### 3. Silver Zone (Phase 4: Transformation → Iceberg)

| Operation | MCP Server | Tool/Method | Priority |
|-----------|------------|-------------|----------|
| **Glue ETL Job** - Bronze→Silver | `aws-dataprocessing-mcp-server` | `create_job` (PySpark + Iceberg), `start_job_run` | PRIMARY |
| **S3 Tables** - Iceberg table mgmt | `s3-tables-mcp-server` | `create_table_bucket`, `create_table`, `update_table` | PRIMARY |
| **Glue Data Quality** - Validation | `aws-dataprocessing-mcp-server` | `create_data_quality_ruleset`, `start_data_quality_rule_run` | PRIMARY |
| **Iceberg Maintenance** - Compaction | `aws-dataprocessing-mcp-server` | Glue ETL job with Iceberg CALL statements | PRIMARY |

### 4. Gold Zone (Phase 4: Curation)

| Operation | MCP Server | Tool/Method | Priority |
|-----------|------------|-------------|----------|
| **Glue ETL Job** - Silver→Gold | `aws-dataprocessing-mcp-server` | `create_job` (aggregations, star schema), `start_job_run` | PRIMARY |
| **S3 Tables** - Gold Iceberg tables | `s3-tables-mcp-server` | `create_table` (fact/dims), `update_table_metadata` | PRIMARY |
| **Athena CTAS** - Materialized views | `aws-dataprocessing-mcp-server` | `start_query_execution` (CREATE TABLE AS) | PRIMARY |
| **Glue Data Quality** - Final check | `aws-dataprocessing-mcp-server` | `start_data_quality_rule_run` (score >= 0.95) | PRIMARY |

### 5. Orchestration (Phase 4: DAG Creation)

| Operation | MCP Server | Tool/Method | Priority |
|-----------|------------|-------------|----------|
| **Step Functions** - State machine | `stepfunctions-tool-mcp-server` | `create_state_machine`, `start_execution` | PRIMARY |
| **Lambda** - Glue job triggers | `lambda-tool-mcp-server` | `create_function`, `invoke_function` | PRIMARY |
| **EventBridge** - Scheduling | LOCAL: `eventbridge-mcp-server` | `put_rule`, `put_targets` | CUSTOM |
| **SNS** - Alerting | `amazon-sns-sqs-mcp-server` | `publish` (failures, SLA breaches) | PRIMARY |

**Note**: Airflow DAGs are generated as Python files but could be deployed via Step Functions for serverless orchestration.

### 6. Semantic Layer Storage

| Component | Storage | MCP Server | Tool/Method | Priority |
|-----------|---------|------------|-------------|----------|
| **SageMaker Catalog** | Glue Catalog + custom metadata | LOCAL: `sagemaker-catalog-mcp-server` | `put_custom_metadata` (column roles, PII, hierarchies) | CUSTOM |
| **SynoDB** (Metrics & SQL Store) | DynamoDB | `dynamodb-mcp-server` | `put_item`, `query`, `scan` (SQL examples) | PRIMARY |
| **Knowledge Graph** | OpenSearch | External: `opensearch-mcp-server` | `index`, `search` (vector embeddings) | EXTERNAL |

### 7. Security & Secrets

| Operation | MCP Server | Tool/Method | Priority |
|-----------|------------|-------------|----------|
| **KMS** - Encryption keys | `core-mcp-server` (AWS SDK) | `kms.create_key`, `kms.encrypt`, `kms.decrypt` | PRIMARY |
| **Secrets Manager** - Credentials | `core-mcp-server` (AWS SDK) | `secretsmanager.get_secret_value`, `put_secret_value` | PRIMARY |
| **IAM** - Roles & policies | `iam-mcp-server` | `create_role`, `attach_role_policy`, `create_policy` | PRIMARY |
| **Lake Formation** - Column-level access | LOCAL: `lakeformation-mcp-server` | `grant_permissions`, `revoke_permissions` | CUSTOM |

### 8. Monitoring & Logging

| Operation | MCP Server | Tool/Method | Priority |
|-----------|------------|-------------|----------|
| **CloudWatch Logs** - Pipeline logs | `cloudwatch-mcp-server` | `put_log_events`, `filter_log_events` | PRIMARY |
| **CloudWatch Metrics** - Quality scores | `cloudwatch-mcp-server` | `put_metric_data` (custom metrics) | PRIMARY |
| **CloudTrail** - Audit logs | `cloudtrail-mcp-server` | `lookup_events` (data access audit) | PRIMARY |
| **Cost Explorer** - Workload costs | `cost-explorer-mcp-server` | `get_cost_and_usage` (tag: workload={name}) | PRIMARY |

### 9. Analytics & Query (Analysis Agent)

| Operation | MCP Server | Tool/Method | Priority |
|-----------|------------|-------------|----------|
| **Athena** - Gold zone queries | `aws-dataprocessing-mcp-server` | `start_query_execution`, `get_query_results` | PRIMARY |
| **Redshift** - Large-scale analytics | `redshift-mcp-server` | `execute_statement`, `get_statement_result` | PRIMARY |
| **SageMaker Catalog** - Metadata lookup | LOCAL: `sagemaker-catalog-mcp-server` | `get_custom_metadata` (column roles for SQL gen) | CUSTOM |
| **SynoDB** - Query pattern search | `dynamodb-mcp-server` | `query` (find similar past queries) | PRIMARY |

---

## MCP Servers Summary

### AWS MCP Servers (Available from awslabs/mcp)

| Server | Package Name | Status | Use Cases |
|--------|--------------|--------|-----------|
| **AWS DataProcessing** | `awslabs.aws-dataprocessing-mcp-server` | ✅ Available | Glue, EMR, Athena — all ETL and cataloging |
| **S3 Tables** | `awslabs.s3-tables-mcp-server` | ✅ Available | Iceberg table management (Silver/Gold zones) |
| **DynamoDB** | `awslabs.dynamodb-mcp-server` | ✅ Available | SynoDB (metrics & SQL store) |
| **Lambda** | `awslabs.lambda-tool-mcp-server` | ✅ Available | Serverless functions for ingestion/triggers |
| **Step Functions** | `awslabs.stepfunctions-tool-mcp-server` | ✅ Available | State machine orchestration |
| **SNS/SQS** | `awslabs.amazon-sns-sqs-mcp-server` | ✅ Available | Alerting and messaging |
| **IAM** | `awslabs.iam-mcp-server` | ✅ Available | Role and policy management |
| **CloudWatch** | `awslabs.cloudwatch-mcp-server` | ✅ Available | Logs, metrics, alarms |
| **CloudTrail** | `awslabs.cloudtrail-mcp-server` | ✅ Available | Audit logging |
| **Cost Explorer** | `awslabs.cost-explorer-mcp-server` | ✅ Available | Cost tracking by workload |
| **Redshift** | `awslabs.redshift-mcp-server` | ✅ Available | Large-scale Gold zone queries |
| **Core (AWS SDK)** | `awslabs.core-mcp-server` | ✅ Available | S3, KMS, Secrets Manager (low-level APIs) |

### Custom MCP Servers (To Be Built)

| Server | Purpose | Implementation | Priority |
|--------|---------|----------------|----------|
| **sagemaker-catalog-mcp-server** | SageMaker Catalog custom metadata operations (column roles, PII, hierarchies) | Python + FastMCP | HIGH |
| **eventbridge-mcp-server** | EventBridge rules and targets for scheduling | Python + FastMCP | MEDIUM |
| **lakeformation-mcp-server** | Lake Formation permissions (column-level access) | Python + FastMCP | MEDIUM |
| **local-filesystem-mcp-server** | Read/write workload config files (YAML) | Python + FastMCP | HIGH |

### External MCP Servers (Third-Party)

| Server | Source | Use Case |
|--------|--------|----------|
| **opensearch-mcp-server** | [opensearch-project/opensearch-mcp-server-py](https://github.com/opensearch-project/opensearch-mcp-server-py) | Knowledge Graph (vector embeddings) |

---

## Installation

### 1. Install AWS MCP Servers

```bash
# Install all required AWS MCP servers via uvx
uvx awslabs.aws-dataprocessing-mcp-server@latest
uvx awslabs.s3-tables-mcp-server@latest
uvx awslabs.dynamodb-mcp-server@latest
uvx awslabs.lambda-tool-mcp-server@latest
uvx awslabs.stepfunctions-tool-mcp-server@latest
uvx awslabs.amazon-sns-sqs-mcp-server@latest
uvx awslabs.iam-mcp-server@latest
uvx awslabs.cloudwatch-mcp-server@latest
uvx awslabs.cloudtrail-mcp-server@latest
uvx awslabs.cost-explorer-mcp-server@latest
uvx awslabs.redshift-mcp-server@latest
uvx awslabs.core-mcp-server@latest
```

### 2. Build Custom MCP Servers

```bash
cd shared/mcp/servers/
python -m pip install fastmcp boto3 pydantic

# Build each custom server
cd sagemaker-catalog-mcp-server && python server.py
cd ../eventbridge-mcp-server && python server.py
cd ../lakeformation-mcp-server && python server.py
cd ../local-filesystem-mcp-server && python server.py
```

### 3. Configure MCP Client

Create `.mcp.json` in the project root (see `.mcp.json` section below).

---

## Step Logging & Visualization

Every MCP call is logged with:

```
════════════════════════════════════════════════════════════════
STEP: Schema Discovery (Glue Crawler)
────────────────────────────────────────────────────────────────
MCP Server: aws-dataprocessing-mcp-server
Tool:       create_crawler
Input:      {crawler_name: "sales_transactions_crawler", ...}
────────────────────────────────────────────────────────────────
Status:     ✓ SUCCESS
Output:     Crawler created. ARN: arn:aws:glue:...
Duration:   2.3s
════════════════════════════════════════════════════════════════
```

All logs are:
- Printed to console with visual separators
- Saved to `logs/mcp/{workload_name}/{timestamp}.log`
- Structured as JSON in `logs/mcp/{workload_name}/{timestamp}.json`

---

## Security Model

All MCP calls:
1. **Authentication**: Use AWS CLI credentials (no hardcoded secrets)
2. **Authorization**: IAM roles with least-privilege policies per agent
3. **Audit**: Every call logged to CloudTrail + local JSON logs
4. **Encryption**: All data at rest (KMS) and in transit (TLS 1.3)
5. **PII Masking**: Sensitive data redacted in logs

---

## Agent → MCP Mapping

| Agent | Primary MCP Servers |
|-------|---------------------|
| **Router Agent** | `local-filesystem-mcp-server` (read workloads/) |
| **Data Onboarding Agent** | All servers (orchestrates sub-agents) |
| **Metadata Agent** | `aws-dataprocessing-mcp-server`, `sagemaker-catalog-mcp-server`, `s3-tables-mcp-server` |
| **Transformation Agent** | `aws-dataprocessing-mcp-server` (Glue ETL), `s3-tables-mcp-server` |
| **Quality Agent** | `aws-dataprocessing-mcp-server` (Glue Data Quality), `cloudwatch-mcp-server` |
| **Analysis Agent** | `aws-dataprocessing-mcp-server` (Athena), `dynamodb-mcp-server` (SynoDB), `sagemaker-catalog-mcp-server` |
| **Orchestration DAG Agent** | `stepfunctions-tool-mcp-server`, `lambda-tool-mcp-server`, `eventbridge-mcp-server`, `amazon-sns-sqs-mcp-server` |

---

## Next Steps

1. **Create `.mcp.json`** - Configure all MCP servers
2. **Build custom servers** - SageMaker Catalog, EventBridge, Lake Formation, Filesystem
3. **Update TOOLS.md** - Add MCP column to all tool reference tables
4. **Update SKILLS.md** - Replace direct AWS SDK calls with MCP tool patterns
5. **Create orchestration layer** - `shared/mcp/orchestrator.py` with visual logging
6. **Test end-to-end** - Run full pipeline via MCP calls only
