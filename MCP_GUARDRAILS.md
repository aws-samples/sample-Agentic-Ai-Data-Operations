# MCP_GUARDRAILS.md — Tool Selection Guardrails for Every Phase

> Prescriptive rules for which tool to use at each pipeline phase.
> MCP tools are the FIRST choice. CLI/local fallback only when MCP is unavailable.
> This file reflects the ACTUAL state of MCP server connectivity — not theoretical.

---

## MCP Server Status (Live)

### Loaded (tools available in main conversation)

| MCP Server | Actual Tool Names | Use For |
|---|---|---|
| **iam** | `mcp__iam__list_roles`, `mcp__iam__simulate_principal_policy`, `mcp__iam__list_role_policies`, `mcp__iam__get_role_policy`, `mcp__iam__put_role_policy`, `mcp__iam__create_role`, `mcp__iam__list_users`, `mcp__iam__get_user`, `mcp__iam__attach_user_policy`, `mcp__iam__attach_group_policy` | Role/policy lookup, permission simulation, least-privilege verification |
| **lambda** | `mcp__lambda__AWS_LambdaFn_LF_access_grant_new`, `mcp__lambda__AWS_Lambda_LF_revoke_access_new`, `mcp__lambda__spark_on_aws_lambda`, `mcp__lambda__tagging_finder`, `mcp__lambda__LF_access_grant` | Lake Formation grants/revokes via Lambda, Spark execution, resource tagging |
| **s3-tables** | S3 Tables (Iceberg) operations | S3 Tables management, Iceberg table operations |
| **cloudtrail** | `mcp__cloudtrail__lookup_events`, `mcp__cloudtrail__lake_query`, `mcp__cloudtrail__list_event_data_stores`, `mcp__cloudtrail__get_query_results`, `mcp__cloudtrail__get_query_status` | Audit trail verification, security investigation, compliance checks |
| **redshift** | `mcp__redshift__list_clusters`, `mcp__redshift__list_databases`, `mcp__redshift__list_schemas`, `mcp__redshift__list_tables`, `mcp__redshift__list_columns`, `mcp__redshift__execute_query` | Query verification on Gold data, schema discovery via Spectrum, data validation |
| **cloudwatch** | Logs, metrics, alarms, dashboards | Monitoring, log queries, metric alarms |
| **cost-explorer** | Cost and usage data | Cost tracking, budget analysis |
| **dynamodb** | Table CRUD, query, scan | SynoDB metrics store, DynamoDB operations |
| **core** | S3, KMS, Secrets Manager | S3 operations, KMS key management, secrets. *Slow startup — may timeout on health check but works in conversation.* |
| **pii-detection** | `detect_pii_in_table`, `scan_database_for_pii`, `create_lf_tags`, `get_pii_columns`, `apply_column_security`, `get_pii_report` | PII detection + LF-Tag application. Custom server. *Slow startup.* |

### Custom Servers (FastMCP, in mcp-servers/)

| MCP Server | Tools | Use For |
|---|---|---|
| **glue-athena** | `create_database`, `get_table`, `get_tables`, `create_crawler`, `start_crawler`, `start_job_run`, `get_job_run`, `athena_query` + 5 more | Glue catalog operations + synchronous Athena queries. Replaces aws-dataprocessing. |
| **lakeformation** | `create_lf_tag`, `list_lf_tags`, `add_lf_tags_to_resource`, `remove_lf_tags_from_resource`, `get_resource_lf_tags`, `grant_permissions`, `revoke_permissions`, `batch_grant_permissions`, `get_lf_tag` | LF-Tags, TBAC grants, column-level security. Replaces Lambda workaround. |
| **sagemaker-catalog** | `put_custom_metadata`, `get_custom_metadata`, `list_tables_with_metadata`, `search_metadata`, `delete_custom_metadata` | Business metadata on Glue tables (column roles, PII flags, hierarchies). |
| **pii-detection** | `detect_pii_in_table`, `scan_database_for_pii`, `create_lf_tags`, `get_pii_columns`, `apply_column_security`, `get_pii_report` | PII detection + LF-Tag application. *Slow startup.* |

### Not Used in Codebase (CLI fallback if ever needed)

| MCP Server | Reason | Fallback |
|---|---|---|
| `sns-sqs` | Not used in production code (comments only) | `aws sns` / `aws sqs` CLI |
| `eventbridge` | Not used in production code | `aws events` CLI |
| `stepfunctions` | Not used (Airflow handles orchestration) | `aws stepfunctions` CLI |

---

## Phase 1: Discovery (Interactive)

> Mostly human interaction. MCP used for checking existing infrastructure.

| Step | MCP Tool (if available) | Fallback | Notes |
|---|---|---|---|
| Check existing Glue databases | `mcp__redshift__execute_query` (via Spectrum external schema) | `aws glue get-databases` CLI | Redshift Spectrum can see Glue catalog |
| Check existing S3 data | `core` MCP (S3 operations) | `aws s3 ls` CLI | core MCP now loaded (slow startup) |
| Verify IAM roles exist | `mcp__iam__list_roles` | `aws iam list-roles` CLI | Check Glue/LF roles before starting |
| Check existing permissions | `mcp__iam__simulate_principal_policy` | `aws iam simulate-principal-policy` CLI | Verify role can access source |
| Audit who accessed source data | `mcp__cloudtrail__lookup_events` | `aws cloudtrail lookup-events` CLI | Security check on source |
| Tag discovery on resources | `mcp__lambda__tagging_finder` | `aws resourcegroupstaggingapi` CLI | Find related tagged resources |

### Guardrail Rules — Phase 1
1. **ALWAYS** check IAM role existence via `mcp__iam__list_roles` before asking discovery questions
2. **ALWAYS** run `mcp__cloudtrail__lookup_events` on the source to check recent access patterns
3. If checking whether data exists in Redshift, use `mcp__redshift__list_tables` — do NOT run CLI
4. For S3 checks, prefer `core` MCP (now loaded); CLI acceptable as fallback if timeout
5. Local workload folder scans use native file tools (Read/Glob/Grep) — never MCP

---

## Phase 2: Dedup & Validate Source

> Source overlap detection + connectivity verification.

| Step | MCP Tool (if available) | Fallback | Notes |
|---|---|---|---|
| Scan existing workloads | Native file tools (Glob/Read) | — | Always local — scan `workloads/*/config/source.yaml` |
| Validate S3 source exists | `core` MCP (S3 operations) | `aws s3 ls` CLI | core MCP now loaded |
| Validate IAM can read source | `mcp__iam__simulate_principal_policy` | `aws iam simulate-principal-policy` CLI | Test `s3:GetObject` on source path |
| Validate Glue role permissions | `mcp__iam__list_role_policies` + `mcp__iam__get_role_policy` | `aws iam list-role-policies` CLI | Inspect attached policies |
| Check for duplicate Glue tables | `mcp__redshift__execute_query` (query `information_schema`) | `aws glue get-tables` CLI | Via Spectrum if external schema exists |
| Audit recent changes to source | `mcp__cloudtrail__lookup_events` (EventName=PutObject) | `aws cloudtrail lookup-events` CLI | Detect if source is actively written to |

### Guardrail Rules — Phase 2
1. **ALWAYS** simulate IAM permissions before attempting source access: `mcp__iam__simulate_principal_policy` with `s3:GetObject`, `s3:ListBucket` on the source ARN
2. **NEVER** proceed to Phase 3 if IAM simulation returns `implicitDeny` — fix permissions first
3. Dedup scan is ALWAYS local file operations — never needs MCP
4. If Redshift Spectrum external schema exists, prefer `mcp__redshift__execute_query` over Glue CLI for catalog checks

---

## Phase 3: Profiling & Metadata Discovery

> Schema discovery + data sampling. Sub-agent generates profiling scripts; main conversation can verify via MCP.

| Step | MCP Tool (if available) | Fallback | Notes |
|---|---|---|---|
| Run Glue Crawler | `glue-athena` MCP | `aws glue create-crawler` + `aws glue start-crawler` CLI | Schema discovery |
| Profile via Athena | `glue-athena` MCP | `aws athena start-query-execution` CLI | 5% sample profiling |
| Profile via Redshift Spectrum | `mcp__redshift__execute_query` | Athena CLI | If external schema exists, query via Spectrum |
| Verify profiling results | `mcp__redshift__list_columns` | `aws glue get-table` CLI | Check discovered schema |
| PII detection | `glue-athena` MCP | Glue ETL `DetectPII` or local regex | |
| Audit profiling operations | `mcp__cloudtrail__lookup_events` (EventName=StartCrawler) | `aws cloudtrail lookup-events` CLI | Verify crawler ran |

### Guardrail Rules — Phase 3
1. **PREFER** `mcp__redshift__execute_query` for profiling if Redshift Spectrum external schema exists — it gives direct SQL results without async polling
2. If no Spectrum schema, fall back to Athena CLI (requires async: start-query → wait → get-results)
3. **ALWAYS** verify schema was registered: use `mcp__redshift__list_tables` (Spectrum) or `aws glue get-table` CLI
4. Sub-agent generates profiling scripts locally — does NOT have MCP access
5. Main conversation executes profiling MCP/CLI calls and feeds results back to sub-agent if needed

---

## Phase 4: Build Pipeline (Sub-Agents)

> Sub-agents generate artifacts locally. NO MCP access in sub-agents.

| Step | Tool | Notes |
|---|---|---|
| Metadata Agent | Local file tools only | Generates `config/semantic.yaml`, `config/source.yaml`, tests |
| Transformation Agent | Local file tools only | Generates `scripts/transform/`, `sql/`, tests |
| Quality Agent | Local file tools only | Generates `config/quality_rules.yaml`, `scripts/quality/`, tests |
| DAG Agent | Local file tools only | Generates `dags/`, tests |
| Test gates | `pytest` via Bash | Run after each sub-agent returns |

### Guardrail Rules — Phase 4
1. **NEVER** call MCP tools from a sub-agent — they don't have access
2. Sub-agents write artifacts + tests to `workloads/{name}/` directories
3. **ALWAYS** run test gate after each sub-agent: `pytest workloads/{name}/tests/ -v`
4. Pipeline scripts reference AWS services (Glue, Athena, S3) but do NOT execute them — execution happens in Phase 5
5. Local integration tests use fixture CSVs in `workloads/{name}/output/` — they simulate what Glue/Athena would produce

---

## Phase 5: Deploy

> Main conversation deploys artifacts to AWS. MCP first, CLI fallback.

### Step 5.1: S3 Upload

| Operation | MCP Tool | Fallback | Status |
|---|---|---|---|
| Upload Bronze data | `core` MCP (S3 operations) | `aws s3 cp` CLI | **MCP** (core now loaded) |
| Upload Silver data | `s3-tables` MCP | `aws s3 cp` CLI | **MCP** (s3-tables now loaded) |
| Upload Gold data | `s3-tables` MCP | `aws s3 cp` CLI | **MCP** (s3-tables now loaded) |
| Upload quarantine | `core` MCP (S3 operations) | `aws s3 cp` CLI | **MCP** (core now loaded) |
| Verify upload | `mcp__cloudtrail__lookup_events` (EventName=PutObject) | `aws s3 ls` CLI | MCP preferred for audit |

### Step 5.2: Glue Catalog Registration

| Operation | MCP Tool | Fallback | Status |
|---|---|---|---|
| Create database | `glue-athena` MCP (`create_database`) | `aws glue create-database` CLI | **MCP** |
| Create tables | `glue-athena` MCP (`create_table`) | `aws glue create-table` CLI | **MCP** |
| Verify tables registered | `mcp__redshift__list_tables` (via Spectrum) | `aws glue get-table` CLI | MCP preferred |
| Verify columns | `mcp__redshift__list_columns` (via Spectrum) | `aws glue get-table` CLI | MCP preferred |
| Audit catalog ops | `mcp__cloudtrail__lookup_events` (EventName=CreateTable) | — | MCP required |

### Step 5.3: IAM & Permissions

| Operation | MCP Tool | Fallback | Status |
|---|---|---|---|
| Find Glue execution role | `mcp__iam__list_roles` | `aws iam list-roles` CLI | **MCP** |
| Verify role permissions | `mcp__iam__simulate_principal_policy` | `aws iam simulate-principal-policy` CLI | **MCP** |
| Inspect inline policies | `mcp__iam__list_role_policies` + `mcp__iam__get_role_policy` | `aws iam list-role-policies` CLI | **MCP** |
| Add inline policy | `mcp__iam__put_role_policy` | `aws iam put-role-policy` CLI | **MCP** |
| Create new role | `mcp__iam__create_role` | `aws iam create-role` CLI | **MCP** |

### Step 5.4: Lake Formation Grants

| Operation | MCP Tool | Fallback | Status |
|---|---|---|---|
| Grant table permissions | `mcp__lambda__AWS_LambdaFn_LF_access_grant_new` | `aws lakeformation grant-permissions` CLI | **MCP (via Lambda)** |
| Revoke permissions | `mcp__lambda__AWS_Lambda_LF_revoke_access_new` | `aws lakeformation revoke-permissions` CLI | **MCP (via Lambda)** |
| Audit LF grants | `mcp__cloudtrail__lookup_events` (EventName=GrantPermissions) | — | **MCP** |

### Step 5.5: Encryption (KMS)

| Operation | MCP Tool | Fallback | Status |
|---|---|---|---|
| Create/verify KMS keys | `core` MCP (KMS operations) | `aws kms create-key` / `aws kms describe-key` CLI | **MCP** (core now loaded) |
| Create key aliases | `core` MCP (KMS operations) | `aws kms create-alias` CLI | **MCP** (core now loaded) |
| Audit KMS operations | `mcp__cloudtrail__lookup_events` (EventName=CreateKey) | — | MCP preferred |

### Step 5.6: Query Verification

| Operation | MCP Tool | Fallback | Status |
|---|---|---|---|
| List Redshift clusters | `mcp__redshift__list_clusters` | — | **MCP** |
| List external schemas | `mcp__redshift__list_schemas` | — | **MCP** |
| Verify tables visible | `mcp__redshift__list_tables` | `aws athena start-query-execution` CLI | **MCP** |
| Run validation query | `mcp__redshift__execute_query` | `aws athena start-query-execution` CLI | **MCP** |
| Star schema join test | `mcp__redshift__execute_query` | Athena CLI | **MCP** |

### Step 5.7: Audit Trail

| Operation | MCP Tool | Fallback | Status |
|---|---|---|---|
| Verify S3 uploads logged | `mcp__cloudtrail__lookup_events` (EventName=PutObject) | — | **MCP** |
| Verify Glue ops logged | `mcp__cloudtrail__lookup_events` (EventName=CreateTable) | — | **MCP** |
| Verify LF grants logged | `mcp__cloudtrail__lookup_events` (EventName=GrantPermissions) | — | **MCP** |
| Verify IAM changes logged | `mcp__cloudtrail__lookup_events` (EventName=PutRolePolicy) | — | **MCP** |
| Complex audit queries | `mcp__cloudtrail__lake_query` (SQL on CloudTrail Lake) | — | **MCP** |

### Guardrail Rules — Phase 5
1. **MCP-FIRST**: For every operation, check the table above. If MCP Tool column has a value, use it. CLI only for "CLI required" rows.
2. **Log every fallback**: When using CLI instead of MCP, print: `Warning: MCP fallback — {server} not loaded for {operation}. Using CLI.`
3. **NEVER** skip audit trail (Step 5.7) — CloudTrail MCP is loaded and must be used
4. **NEVER** skip permission verification (Step 5.3) — IAM MCP is loaded and must be used
5. **ALWAYS** verify deployment via query (Step 5.6) — Redshift MCP is loaded, use it over Athena CLI
6. **ALWAYS** run steps in order: S3 Upload → Glue Catalog → IAM → Lake Formation → KMS → Query Verify → Audit
7. **If deployment fails**: Do NOT retry automatically. Report failure with full context (step, tool, error) and ask human how to proceed.

---

## Local Mode (Current Default)

When running locally (no AWS target), the deploy phase operates in **simulation mode**:

1. Pipeline artifacts stay in `workloads/{name}/output/` (Silver, Gold, quarantine, quality reports)
2. MCP calls that **are loaded** (IAM, Lambda, S3-Tables, CloudTrail, Redshift, CloudWatch, Cost-Explorer, DynamoDB, Core, PII-Detection) execute against the real AWS account
3. CLI fallback calls are **logged but not executed** — printed as `[DRY-RUN] aws glue create-table ...`
4. Local `.iceberg_metadata` sidecar files simulate Iceberg table registration

To switch to **live deploy mode**, set environment variable:
```bash
export DEPLOY_MODE=live  # Execute all CLI fallback commands
export DEPLOY_MODE=local  # Default — dry-run CLI, live MCP
```

---

## MCP Call Summary Template

After every deploy, present this summary:

```
Deploy Summary: {workload_name}
===============================

MCP Calls (live):
  iam:            {count} calls  (list_roles, simulate_principal_policy, ...)
  lambda:         {count} calls  (LF_access_grant_new, ...)
  s3-tables:      {count} calls  (Iceberg table operations, ...)
  cloudtrail:     {count} calls  (lookup_events, ...)
  redshift:       {count} calls  (execute_query, list_tables, ...)
  cloudwatch:     {count} calls  (log queries, metrics, ...)
  cost-explorer:  {count} calls  (cost analysis, ...)
  dynamodb:       {count} calls  (SynoDB queries, ...)
  core:           {count} calls  (S3 ops, KMS, Secrets Manager, ...)
  pii-detection:  {count} calls  (detect_pii, apply_tags, ...)

CLI Fallback (dry-run in local mode):
  aws glue:    {count} calls  (Reason: aws-dataprocessing not on PyPI)
  aws athena:  {count} calls  (Reason: aws-dataprocessing not on PyPI)
  aws lf:      {count} calls  (Reason: lakeformation dependency conflict)

Total: {mcp_count} MCP + {cli_count} CLI = {total} operations
MCP Coverage: {mcp_pct}%
```

---

## MCP Server Installation

All servers are configured in `.mcp.json` using `uvx` (uv tool runner) which auto-manages Python 3.12+ environments.

### Currently Installed (10 servers)

| Server | Package | Command |
|---|---|---|
| `iam` | `awslabs-iam-mcp-server` | `uvx --from awslabs-iam-mcp-server awslabs.iam-mcp-server` |
| `lambda` | `awslabs-lambda-mcp-server` | `uvx --from awslabs-lambda-mcp-server awslabs.lambda-mcp-server` |
| `s3-tables` | `awslabs-s3-tables-mcp-server` | `uvx --from awslabs-s3-tables-mcp-server awslabs.s3-tables-mcp-server` |
| `cloudtrail` | `awslabs-cloudtrail-mcp-server` | `uvx --from awslabs-cloudtrail-mcp-server awslabs.cloudtrail-mcp-server` |
| `redshift` | `awslabs-redshift-mcp-server` | `uvx --from awslabs-redshift-mcp-server awslabs.redshift-mcp-server` |
| `cloudwatch` | `awslabs-cloudwatch-mcp-server` | `uvx --from awslabs-cloudwatch-mcp-server awslabs.cloudwatch-mcp-server` |
| `cost-explorer` | `awslabs-cost-explorer-mcp-server` | `uvx --from awslabs-cost-explorer-mcp-server awslabs.cost-explorer-mcp-server` |
| `dynamodb` | `awslabs-dynamodb-mcp-server` | `uvx --from awslabs-dynamodb-mcp-server awslabs.dynamodb-mcp-server` |
| `core` | `awslabs-core-mcp-server` | `uvx --from awslabs-core-mcp-server awslabs.core-mcp-server` |
| `pii-detection` | Custom server | `uv run --no-project --with boto3 --with mcp --python 3.13 mcp-servers/pii-detection-server/server.py` |

### Not Available on PyPI

| Server | Reason | Workaround |
|---|---|---|
| `aws-dataprocessing` (Glue/Athena) | No PyPI package exists | `aws glue` / `aws athena` CLI |
| `sagemaker-catalog` | No PyPI package exists | `aws glue` CLI with custom metadata properties |

### Dependency Conflicts (uvx cannot resolve)

| Server | Reason | Workaround |
|---|---|---|
| `lakeformation` | `awslabs-lakeformation-mcp-server` has dependency conflicts | `lambda` MCP (`LF_access_grant_new`) or `aws lakeformation` CLI |
| `sns-sqs` | `awslabs-sns-sqs-mcp-server` has dependency conflicts | `aws sns` / `aws sqs` CLI |
| `eventbridge` | `awslabs-eventbridge-mcp-server` has dependency conflicts | `aws events` CLI |
| `stepfunctions` | `awslabs-stepfunctions-mcp-server` has dependency conflicts | `aws stepfunctions` CLI |

### Test connectivity

```bash
# Health check all servers
claude mcp list

# Test a specific server
uvx --from awslabs-iam-mcp-server awslabs.iam-mcp-server --help
uvx --from awslabs-core-mcp-server awslabs.core-mcp-server --help

# Note: core and pii-detection have slow startup (~5-10s)
# Health check may timeout but they work fine in conversation
```
