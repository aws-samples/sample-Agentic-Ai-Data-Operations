# Pipeline Guardrails

Runtime rules the pipeline checks at each step. When a guardrail is hit, the pipeline logs `[GUARDRAIL]` but does **NOT** stop. Violations are collected and reported in the final summary.

---

## Guardrail Format

Each guardrail has the following attributes:

| Attribute | Description |
|---|---|
| **Code** | Unique identifier (e.g., `SEC-001`) |
| **Name** | Short descriptive name |
| **Category** | Security, Data Quality, Integrity, or Operational |
| **Description** | What the guardrail checks |
| **Check Logic** | How the check is performed |
| **When Checked** | Pipeline step(s) where this guardrail runs |
| **PASS Example** | What a passing check looks like |
| **FAIL Example** | What a failing check looks like |

---

## Security Guardrails

### SEC-001: No Hardcoded Secrets

| Attribute | Value |
|---|---|
| **Category** | Security |
| **Description** | Scan scripts, configs, and DAG files for patterns that match AWS access keys, secret keys, passwords, tokens, or connection strings. |
| **Check Logic** | Regex scan for patterns: `AKIA[0-9A-Z]{16}`, `[0-9a-zA-Z/+=]{40}`, `password\s*=\s*['"]`, `jdbc:.*@`, `Bearer\s+[A-Za-z0-9\-._~+/]+=*`. Scan all files in `workloads/{name}/config/`, `workloads/{name}/scripts/`, and `workloads/{name}/dags/`. |
| **When Checked** | Step 1 (pipeline initialization), Step 6 (before Staging write), Step 10 (before Publish write) |
| **PASS** | `[GUARDRAIL SEC-001] No hardcoded secrets in workload files ... PASS` |
| **FAIL** | `[GUARDRAIL SEC-001] Potential secret found in scripts/transform/landing_to_staging.py line 42 ... FAIL` |

### SEC-002: KMS Key Alias Validated

| Attribute | Value |
|---|---|
| **Category** | Security |
| **Description** | Confirm the KMS alias exists and the key is in "Enabled" state before any encrypt/decrypt operation. |
| **Check Logic** | Call `kms.describe_key(KeyId=alias)` and verify `KeyMetadata.KeyState == "Enabled"`. If the alias does not resolve, the check fails. |
| **When Checked** | Step 2 (Landing encrypt), Step 6 (Staging encrypt), Step 10 (Publish encrypt) |
| **PASS** | `[GUARDRAIL SEC-002] KMS key alias validated: alias/staging-data-key ... PASS` |
| **FAIL** | `[GUARDRAIL SEC-002] KMS alias not found: alias/staging-data-key ... FAIL` |

### SEC-003: PII Columns Masked

| Attribute | Value |
|---|---|
| **Category** | Security |
| **Description** | Verify that columns flagged as PII in `semantic.yaml` have hashing or redaction applied before data is promoted to Staging. |
| **Check Logic** | Read `semantic.yaml` for columns with `pii: true`. After transformation, sample 10 rows from the output and verify PII columns contain only hashed values (SHA-256 pattern) or redacted placeholders (`***REDACTED***`). Raw values must not appear. |
| **When Checked** | Step 7 (after Landing-to-Staging transformation) |
| **PASS** | `[GUARDRAIL SEC-003] PII columns masked: email (SHA-256), phone (SHA-256) ... PASS` |
| **FAIL** | `[GUARDRAIL SEC-003] PII column 'email' contains raw values in Staging output ... FAIL` |

### SEC-004: TLS 1.3 Enforced

| Attribute | Value |
|---|---|
| **Category** | Security |
| **Description** | Verify that all data transfers use TLS 1.3 or higher. |
| **Check Logic** | In production: inspect the SSL context on all boto3 sessions and HTTP connections. Locally: check that S3 endpoint URLs use `https://`. This guardrail is informational in local/test mode. |
| **When Checked** | Step 2 (Landing upload), Step 6 (Staging write), Step 10 (Publish write) |
| **PASS** | `[GUARDRAIL SEC-004] TLS 1.3 enforced (production) / TLS check skipped (local) ... PASS` |
| **FAIL** | `[GUARDRAIL SEC-004] Non-TLS endpoint detected: http://s3.amazonaws.com ... FAIL` |

---

## Data Quality Guardrails

### DQ-001: Quality Gate Threshold Met

| Attribute | Value |
|---|---|
| **Category** | Data Quality |
| **Description** | Overall quality score must meet the zone threshold: Staging >= 0.80, Publish >= 0.95. |
| **Check Logic** | Run all quality rules (completeness, accuracy, consistency, validity, uniqueness). Compute weighted average score. Compare against threshold. |
| **When Checked** | Step 8 (before Staging promotion), Step 11 (before Publish promotion) |
| **PASS** | `[GUARDRAIL DQ-001] Staging quality gate: 0.9231 >= 0.80 ............ PASS` |
| **FAIL** | `[GUARDRAIL DQ-001] Staging quality gate: 0.72 >= 0.80 ............ FAIL` |

### DQ-002: No Critical Rule Failures

| Attribute | Value |
|---|---|
| **Category** | Data Quality |
| **Description** | Critical rules (PK not-null, PK unique) must pass regardless of overall score. A dataset can score 0.99 overall but still fail if the primary key has duplicates. |
| **Check Logic** | Evaluate rules tagged `severity: critical` in `quality_rules.yaml`. If any critical rule returns `FAIL`, this guardrail fails even if DQ-001 passes. |
| **When Checked** | Step 8 (before Staging promotion), Step 11 (before Publish promotion) |
| **PASS** | `[GUARDRAIL DQ-002] Critical rules: PK not-null PASS, PK unique PASS ... PASS` |
| **FAIL** | `[GUARDRAIL DQ-002] Critical rule failure: PK unique FAIL (47 duplicates found) ... FAIL` |

### DQ-003: No Data Dropped Silently

| Attribute | Value |
|---|---|
| **Category** | Data Quality |
| **Description** | Every rejected row must appear in the quarantine table with an error reason. The sum of output rows + quarantine rows must equal input rows. |
| **Check Logic** | `input_count == output_count + quarantine_count`. If the equation does not balance, rows were silently dropped. |
| **When Checked** | Step 7 (after Landing-to-Staging transform), Step 9 (after Staging-to-Publish transform) |
| **PASS** | `[GUARDRAIL DQ-003] Row accounting: 1000 input = 962 output + 38 quarantine ... PASS` |
| **FAIL** | `[GUARDRAIL DQ-003] Row accounting: 1000 input != 955 output + 38 quarantine (7 missing) ... FAIL` |

### DQ-004: Row Count Within Expected Range

| Attribute | Value |
|---|---|
| **Category** | Data Quality |
| **Description** | Output must not be empty, and row count must not deviate more than 20% from the historical baseline (if one exists). |
| **Check Logic** | Check `output_count > 0`. If a baseline exists (from previous runs), verify `abs(output_count - baseline) / baseline <= 0.20`. |
| **When Checked** | Step 7 (after Landing-to-Staging transform), Step 9 (after Staging-to-Publish transform) |
| **PASS** | `[GUARDRAIL DQ-004] Row count 1042 within 20% of baseline 1000 ... PASS` |
| **FAIL** | `[GUARDRAIL DQ-004] Row count 0 (empty output) ... FAIL` |

---

## Integrity Guardrails

### INT-001: Landing Zone Immutability

| Attribute | Value |
|---|---|
| **Category** | Integrity |
| **Description** | Landing zone data must never be modified after initial write. Any attempt to update, delete, or overwrite an existing Landing object is a violation. |
| **Check Logic** | Before any write to Landing, check if the target key already exists in S3. If it does, block the write. Also verify S3 versioning is enabled on the Landing bucket. |
| **When Checked** | Step 2 (Landing ingestion), Step 3 (Landing verification) |
| **PASS** | `[GUARDRAIL INT-001] Landing zone immutability: no overwrites detected ... PASS` |
| **FAIL** | `[GUARDRAIL INT-001] Landing zone immutability: attempted overwrite of s3://bucket/landing/orders/2026-03-15/data.csv ... FAIL` |

### INT-002: FK Referential Integrity

| Attribute | Value |
|---|---|
| **Category** | Integrity |
| **Description** | Foreign key relationships defined in `semantic.yaml` must have a validity rate at or above the configured threshold (default >= 0.90). |
| **Check Logic** | For each FK relationship, run a LEFT JOIN between the child and parent table on the FK column. Calculate `valid_count / total_count`. Compare against threshold from config. |
| **When Checked** | Step 9 (Staging-to-Publish transform, after join enrichment) |
| **PASS** | `[GUARDRAIL INT-002] FK integrity: orders.customer_id -> customers.customer_id: 0.9847 >= 0.90 ... PASS` |
| **FAIL** | `[GUARDRAIL INT-002] FK integrity: orders.customer_id -> customers.customer_id: 0.8521 >= 0.90 ... FAIL` |

### INT-003: Derived Column Formula Verified

| Attribute | Value |
|---|---|
| **Category** | Integrity |
| **Description** | Computed/derived columns (e.g., `total_amount = quantity * unit_price`) must match their formula within a tolerance of 1%. |
| **Check Logic** | For each column with `derived_from` in `semantic.yaml`, recompute the value from source columns and compare. Calculate `max(abs(actual - expected) / expected)` across all rows. Must be <= 0.01. |
| **When Checked** | Step 9 (after Staging-to-Publish transform) |
| **PASS** | `[GUARDRAIL INT-003] Derived column 'total_amount' formula verified (max deviation: 0.0%) ... PASS` |
| **FAIL** | `[GUARDRAIL INT-003] Derived column 'total_amount' formula deviation: 3.2% (tolerance: 1%) ... FAIL` |

### INT-004: Schema Enforcement

| Attribute | Value |
|---|---|
| **Category** | Integrity |
| **Description** | Output datasets must exactly match the expected schema -- no unexpected columns added, no expected columns missing, no type mismatches. |
| **Check Logic** | Compare output DataFrame columns and types against the schema defined in `semantic.yaml`. Flag any column present in output but not in schema (unexpected), or in schema but not in output (missing). |
| **When Checked** | Step 7 (after Landing-to-Staging transform), Step 9 (after Staging-to-Publish transform) |
| **PASS** | `[GUARDRAIL INT-004] Schema enforcement: 16/16 columns match expected schema ... PASS` |
| **FAIL** | `[GUARDRAIL INT-004] Schema enforcement: unexpected column 'temp_calc' in Staging output ... FAIL` |

---

## Operational Guardrails

### OPS-001: Idempotency

| Attribute | Value |
|---|---|
| **Category** | Operational |
| **Description** | Running the same pipeline step twice with the same input must produce identical output. No duplicate records, no side effects. |
| **Check Logic** | Compute a checksum (SHA-256) of the output after the first run. Run the same step again. Compare checksums. They must match. |
| **When Checked** | Step 7 (Landing-to-Staging), Step 9 (Staging-to-Publish) |
| **PASS** | `[GUARDRAIL OPS-001] Idempotency: re-run checksum matches (SHA-256: a1b2c3...) ... PASS` |
| **FAIL** | `[GUARDRAIL OPS-001] Idempotency: re-run produced different output (row count diff: +12) ... FAIL` |

### OPS-002: Encryption Re-keyed at Zone Boundary

| Attribute | Value |
|---|---|
| **Category** | Operational |
| **Description** | Data must be re-encrypted with the destination zone's KMS key when crossing a zone boundary. Landing data encrypted with `alias/landing-data-key` must be re-encrypted with `alias/staging-data-key` when written to Staging. |
| **Check Logic** | After writing to the destination zone, call `s3.head_object` and verify `SSEKMSKeyId` matches the expected zone key alias. |
| **When Checked** | Step 6 (Landing-to-Staging write), Step 10 (Staging-to-Publish write) |
| **PASS** | `[GUARDRAIL OPS-002] Encryption re-keyed: Staging output uses alias/staging-data-key ... PASS` |
| **FAIL** | `[GUARDRAIL OPS-002] Encryption mismatch: Staging output still uses alias/landing-data-key ... FAIL` |

### OPS-003: Audit Log Entry Written

| Attribute | Value |
|---|---|
| **Category** | Operational |
| **Description** | Every data movement (read, write, transform, quality check) must produce an audit log entry with: who (agent/user ID), what (operation), when (ISO 8601 timestamp), where (source/target dataset). |
| **Check Logic** | After each pipeline step, verify an audit log entry exists with all four required fields populated. Logs are append-only. |
| **When Checked** | Every step (1-12) |
| **PASS** | `[GUARDRAIL OPS-003] Audit log entry written: transform/landing_to_staging at 2026-03-15T10:30:00Z ... PASS` |
| **FAIL** | `[GUARDRAIL OPS-003] Audit log entry missing for step 7 (Landing-to-Staging transform) ... FAIL` |

### OPS-004: Iceberg Metadata Sidecar Generated

| Attribute | Value |
|---|---|
| **Category** | Operational |
| **Description** | Staging and Publish outputs must include an Iceberg metadata sidecar file (`.iceberg_metadata`) recording format version, compression, partition spec, and snapshot info. |
| **Check Logic** | After writing Staging/Publish output, check that a `.iceberg_metadata` file exists alongside the data. Validate it contains required fields: `format_version`, `compression`, `partition_spec`, `snapshot_id`. |
| **When Checked** | Step 7 (after Staging write), Step 10 (after Publish write) |
| **PASS** | `[GUARDRAIL OPS-004] Iceberg metadata sidecar generated: staging/orders/.iceberg_metadata ... PASS` |
| **FAIL** | `[GUARDRAIL OPS-004] Iceberg metadata sidecar missing for publish/orders/ ... FAIL` |

---

## Pipeline Step Mapping

Which guardrails are checked at which pipeline step:

| Step | Description | Guardrails Checked |
|---|---|---|
| 1 | Pipeline initialization | SEC-001 |
| 2 | Landing zone ingestion | SEC-002, SEC-004, INT-001 |
| 3 | Landing verification | INT-001, OPS-003 |
| 4 | Glue Crawler (schema discovery) | OPS-003 |
| 5 | Landing-to-Staging transform | OPS-003 |
| 6 | Staging encrypt and write | SEC-001, SEC-002, SEC-004, OPS-002 |
| 7 | Staging output validation | SEC-003, DQ-003, DQ-004, INT-004, OPS-001, OPS-003, OPS-004 |
| 8 | Staging quality gate | DQ-001, DQ-002 |
| 9 | Staging-to-Publish transform | DQ-003, DQ-004, INT-002, INT-003, INT-004, OPS-001, OPS-003 |
| 10 | Publish encrypt and write | SEC-001, SEC-002, SEC-004, OPS-002, OPS-004 |
| 11 | Publish quality gate | DQ-001, DQ-002 |
| 12 | Pipeline summary and cleanup | OPS-003 |
| 13 | MWAA DAG upload | SEC-001, OPS-003 |
| 14 | Post-deployment verification | DQ-001, SEC-004, OPS-003, OPS-004 |

---

## Log Output Format

### During Pipeline Execution

Each guardrail check produces a single log line:

```
  [GUARDRAIL SEC-001] No hardcoded secrets in workload files .......... PASS
  [GUARDRAIL SEC-002] KMS key alias validated: alias/landing-data-key . PASS
  [GUARDRAIL INT-001] Landing zone immutability: no overwrites ........ PASS
  [GUARDRAIL OPS-003] Audit log entry written: ingest/landing ......... PASS
```

On failure, an additional context line is logged:

```
  [GUARDRAIL DQ-001] Staging quality gate: 0.72 >= 0.80 .............. FAIL
  >>> Guardrail violation logged. Pipeline continues but will report in summary.

  [GUARDRAIL INT-002] FK integrity: orders.customer_id: 0.85 >= 0.90 . FAIL
  >>> Guardrail violation logged. Pipeline continues but will report in summary.
```

### Final Summary Table

At the end of every pipeline run, a summary table is printed:

```
================================================================================
  GUARDRAIL SUMMARY: order_transactions (2026-03-15T10:45:00Z)
================================================================================

  Code     | Name                          | Steps Checked | Result
  ---------|-------------------------------|---------------|--------
  SEC-001  | No hardcoded secrets          | 1, 6, 10      | PASS
  SEC-002  | KMS key alias validated       | 2, 6, 10      | PASS
  SEC-003  | PII columns masked            | 7              | PASS
  SEC-004  | TLS 1.3 enforced              | 2, 6, 10      | PASS
  DQ-001   | Quality gate threshold met    | 8, 11          | PASS
  DQ-002   | No critical rule failures     | 8, 11          | PASS
  DQ-003   | No data dropped silently      | 7, 9           | PASS
  DQ-004   | Row count within range        | 7, 9           | PASS
  INT-001  | Landing zone immutability     | 2, 3           | PASS
  INT-002  | FK referential integrity      | 9              | FAIL
  INT-003  | Derived column formula         | 9              | PASS
  INT-004  | Schema enforcement            | 7, 9           | PASS
  OPS-001  | Idempotency                   | 7, 9           | PASS
  OPS-002  | Encryption re-keyed           | 6, 10          | PASS
  OPS-003  | Audit log entry written       | 1-12           | PASS
  OPS-004  | Iceberg metadata sidecar      | 7, 10          | PASS

  Total: 16 guardrails | 15 PASS | 1 FAIL
  Failures: INT-002 (FK integrity: orders.customer_id -> customers.customer_id: 0.85)

================================================================================
```

### Guardrail Violation Detail (appended after summary on FAIL)

```
  GUARDRAIL VIOLATIONS:
  ---------------------

  [INT-002] FK Referential Integrity
    Step:        9 (Staging-to-Publish transform)
    Relationship: orders.customer_id -> customers.customer_id
    Expected:    >= 0.90
    Actual:      0.8521
    Orphan rows: 148 of 1000
    Action:      148 rows quarantined to staging/orders/quarantine/fk_orphans/

================================================================================
```

---

## Cedar Policy Engine

All 16 guardrails are implemented as **Cedar policies** evaluated via Amazon Verified Permissions (AVP) in production or `cedarpy` locally.

### Architecture

```
Pipeline Runner  -->  CedarPolicyEvaluator  -->  AVP (production) / cedarpy (local)
                           |
                      CloudTrail (automatic decision logging)
```

### Policy Files

| Directory | Content |
|---|---|
| `shared/policies/schema.cedarschema` | Entity types, actions, context shapes |
| `shared/policies/guardrails/*.cedar` | 16 guardrail `forbid` policies |
| `shared/policies/agent_authorization/*.cedar` | 7 agent `permit`/`forbid` policies |
| `shared/policies/templates/` | Per-workload parameterized templates |

### Evaluation Modes

| Mode | Env Var | Engine | Usage |
|---|---|---|---|
| `local` (default) | `CEDAR_MODE=local` | cedarpy / JSON fallback | Dev, tests, local pipelines |
| `avp` | `CEDAR_MODE=avp` | boto3 `verifiedpermissions.is_authorized()` | Deployed Airflow DAGs |

### How It Works

1. Python runs the actual check logic (regex scans, row counts, checksums, etc.)
2. Python passes boolean results + attributes into Cedar **context**
3. Cedar `forbid` policies evaluate the context and make the Allow/Deny decision
4. Cedar decision is **authoritative** — overrides the inline `passed` parameter

### Output Format

Each guardrail check now shows the evaluation engine:

```
  [GUARDRAIL SEC-002] KMS key alias validated: alias/landing-data-key . PASS [local]
  [GUARDRAIL DQ-001] Staging quality gate: 0.72 >= 0.80 .............. FAIL [local]
  >>> Cedar: Fallback: quality 72 < 80
```

The summary table includes an Engine column:

```
  Code         Description                                Result Engine
  ----------   ----------------------------------------   ------ --------
  SEC-002      KMS key alias validated: alias/landing-d   PASS   local
  DQ-001       Staging quality gate: 0.72 >= 0.80         FAIL   local
```

---

## Phase 5 Deployment Guardrails

Phase 5 introduces deployment-specific guardrails that ensure the pipeline is production-ready before going live.

### DAG Syntax Valid

| Attribute | Value |
|---|---|
| **Category** | Operational |
| **Description** | DAG file must parse without Python syntax errors. All imports must resolve, no undefined variables. |
| **Check Logic** | Run `python -m py_compile dags/{workload_name}_dag.py`. Check exit code. If non-zero, parse stderr for syntax error details. |
| **When Checked** | Step 13 (before MWAA DAG upload) |
| **PASS** | `[DEPLOYMENT] DAG syntax validated: dags/order_transactions_dag.py ... PASS` |
| **FAIL** | `[DEPLOYMENT] DAG syntax error: line 42, undefined variable 'bucket_nme' ... FAIL` |

### Airflow Variables Set

| Attribute | Value |
|---|---|
| **Category** | Operational |
| **Description** | All `Variable.get()` calls in the DAG must either have `default_var` argument OR the Variable must exist in MWAA. No missing variables at runtime. |
| **Check Logic** | Parse the DAG file for `Variable.get('key')` patterns. Extract all keys. Check if each key exists in MWAA (via `airflow variables list`) or has a `default_var` parameter. |
| **When Checked** | Step 13 (before MWAA DAG upload) |
| **PASS** | `[DEPLOYMENT] Airflow variables validated: 5/5 variables exist or have defaults ... PASS` |
| **FAIL** | `[DEPLOYMENT] Missing Airflow variable: 'staging_bucket' (no default_var) ... FAIL` |

### Smoke Test Suite Passes

| Attribute | Value |
|---|---|
| **Category** | Data Quality, Security, Operational |
| **Description** | All 8 post-deployment verification checks must pass before deployment is considered complete: Glue tables registered, Athena query succeeds, Lake Formation LF-Tags applied, TBAC grants active, KMS encryption verified, MWAA DAG imported, QuickSight dashboard accessible, CloudTrail logging active. |
| **Check Logic** | Run the verification suite in `run_pipeline.py` Step 14. Each check has pass/fail criteria. Overall deployment passes only if all 8 checks pass. |
| **When Checked** | Step 14 (post-deployment verification) |
| **PASS** | `[DEPLOYMENT] Smoke test suite: 8/8 checks passed ... PASS` |
| **FAIL** | `[DEPLOYMENT] Smoke test suite: 6/8 checks passed (Athena query failed, QuickSight dashboard not found) ... FAIL` |

### No Secrets in DAG

| Attribute | Value |
|---|---|
| **Category** | Security |
| **Description** | DAG file must not contain hardcoded credentials, AWS account IDs, S3 bucket names, or connection strings. All config must come from Airflow Variables or Connections. |
| **Check Logic** | Scan DAG file with the same regex patterns as SEC-001. Additionally check for patterns: `\d{12}` (account ID), `s3://[a-z0-9\-]+` (bucket name), `arn:aws:` (ARN). |
| **When Checked** | Step 13 (before MWAA DAG upload) |
| **PASS** | `[DEPLOYMENT] No secrets in DAG: dags/order_transactions_dag.py ... PASS` |
| **FAIL** | `[DEPLOYMENT] Hardcoded value in DAG line 28: s3://my-bucket-123456789012 ... FAIL` |

**Note**: Regulation-specific controls in `prompts/regulation/` (GDPR, CCPA, HIPAA, SOX, PCI DSS) add additional guardrails when loaded. These augment the base 16 guardrails with compliance-specific checks such as data retention policies, consent tracking, breach notification procedures, and audit trail requirements.

---

## Adding Custom Guardrails

To add a new guardrail:

1. Choose a category prefix: `SEC-`, `DQ-`, `INT-`, or `OPS-`
2. Assign the next available number (e.g., `SEC-005`)
3. Define all attributes (Code, Name, Category, Description, Check Logic, When Checked, PASS/FAIL examples)
4. Add the guardrail to the Pipeline Step Mapping table
5. Create a Cedar policy file in `shared/policies/guardrails/` (follow existing pattern)
6. Add the context fields to `shared/policies/schema.cedarschema`
7. Add fallback logic to `_fallback_evaluate()` in `shared/utils/cedar_client.py`
8. Update the guardrail action map in `cedar_client.py` (`GUARDRAIL_ACTION_MAP`)
9. Add tests in `shared/tests/test_cedar_policies.py`

Guardrail checks are non-blocking by design. If you need a blocking check (pipeline must stop on failure), use the Quality Gate mechanism instead (see `quality_rules.yaml`).
