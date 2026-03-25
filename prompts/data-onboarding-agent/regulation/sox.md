# SOX Compliance Controls

> Use this prompt ONLY when SOX compliance is explicitly required.
> NOT applied by default — triggered when user selects SOX during discovery.

## When to Use

- User selects SOX during Phase 1 discovery
- User asks "does this comply with SOX?"
- Workload config has `compliance: [SOX]` in quality_rules.yaml
- Data contains financial statements, accounting records, or transaction data

## Prerequisites

Before applying SOX controls, verify these AWS resources exist:

| Resource | Check Command | What If Missing? |
|----------|---------------|------------------|
| **KMS key** `alias/{workload}-sox-key` | `aws kms describe-key --key-id alias/{workload}-sox-key --region us-east-1` | Run `prompts/environment-setup-agent/01-setup-aws-infrastructure.md` Step 4, or create manually: `aws kms create-key --description "SOX financial data encryption key for {workload}"` then `aws kms create-alias --alias-name alias/{workload}-sox-key --target-key-id {KEY_ID}` |
| **IAM role** `AuditorRole` | `aws iam get-role --role-name AuditorRole` | Create with trust policy for Lake Formation (read-only): `aws iam create-role --role-name AuditorRole --assume-role-policy-document file://trust-policy.json` |
| **IAM role** `FinanceRole` | `aws iam get-role --role-name FinanceRole` | Create with trust policy for Lake Formation and Glue |
| **IAM role** `ExternalReviewerRole` | `aws iam get-role --role-name ExternalReviewerRole` | Create with trust policy for Lake Formation (read-only, LOW sensitivity only) |
| **IAM role** `DashboardUserRole` | `aws iam get-role --role-name DashboardUserRole` | Create with trust policy for QuickSight and Athena |
| **LF-Tag** `PII_Classification` | `aws lakeformation list-lf-tags --region us-east-1 \| grep PII_Classification` | Run `prompts/environment-setup-agent/01-setup-aws-infrastructure.md` Step 6, or create manually: `aws lakeformation create-lf-tag --tag-key PII_Classification --tag-values CRITICAL,HIGH,MEDIUM,LOW,NONE` |
| **LF-Tag** `PII_Type` | `aws lakeformation list-lf-tags --region us-east-1 \| grep PII_Type` | Create: `aws lakeformation create-lf-tag --tag-key PII_Type --tag-values SSN,EMAIL,PHONE,ADDRESS,DOB,NATIONAL_ID,NAME,FINANCIAL_ACCOUNT` |
| **LF-Tag** `Data_Sensitivity` | `aws lakeformation list-lf-tags --region us-east-1 \| grep Data_Sensitivity` | Create: `aws lakeformation create-lf-tag --tag-key Data_Sensitivity --tag-values CRITICAL,HIGH,MEDIUM,LOW` |
| **CloudTrail** enabled | `aws cloudtrail get-trail-status --name {TRAIL} --region us-east-1` | Enable CloudTrail in AWS Console or via CLI. SOX requires audit trail for all financial data access and modifications. |
| **S3 audit bucket** with Object Lock | `aws s3api get-object-lock-configuration --bucket {AUDIT_BUCKET}` | Create immutable audit bucket: `aws s3api create-bucket --bucket {AUDIT_BUCKET} --object-lock-enabled-for-bucket --region us-east-1`. SOX requires 7-year retention. |

**Quick check** (run this before applying SOX controls):
```bash
# Check if key exists (replace {workload} with your workload name)
aws kms describe-key --key-id alias/{workload}-sox-key --region us-east-1 && echo "✓ KMS key exists" || echo "✗ KMS key missing"

# Check if roles exist
for ROLE in AuditorRole FinanceRole ExternalReviewerRole DashboardUserRole; do
  aws iam get-role --role-name $ROLE >/dev/null 2>&1 && echo "✓ $ROLE exists" || echo "✗ $ROLE missing"
done

# Check if LF-Tags exist
aws lakeformation list-lf-tags --region us-east-1 --query 'LFTags[].TagKey' --output text | grep -E 'PII_Classification|PII_Type|Data_Sensitivity' && echo "✓ LF-Tags exist" || echo "✗ LF-Tags missing"
```

**If prerequisites are missing**: Run the environment setup first (`prompts/environment-setup-agent/01-setup-aws-infrastructure.md`) or create resources manually using the commands above. Do NOT proceed with SOX onboarding until all prerequisites pass.

## Controls Applied

### 1. PII Detection

SOX is primarily about **financial data integrity**, not PII. However, financial data often contains personally identifiable information:

| PII Type | SOX Relevance | Sensitivity |
|----------|--------------|-------------|
| NAME (manager_name, employee_name) | Audit trail attribution | MEDIUM |
| EMAIL | Audit trail attribution | MEDIUM |
| FINANCIAL_ACCOUNT | Financial integrity | CRITICAL |
| All financial measures (revenue, cost, price) | Core SOX scope | NONE (but quality gate at 0.95) |

### 2. Data Retention

- Audit logs: **2555 days** (7 years) — SOX Section 802 requirement
- Financial records: **2555 days** (7 years minimum)
- All change history must be preserved (no deletion of audit trail)
- Bronze zone immutability is critical — source financial records must never be modified

### 3. Access Control

| Role | Sensitivity Access | Purpose |
|------|-------------------|---------|
| Auditor | ALL (read-only) | External/internal audit |
| Finance Team | NONE + LOW + MEDIUM | Financial reporting |
| External Reviewer | NONE + LOW | Aggregated financials only |
| Dashboard User | NONE + LOW | Executive reporting |

**Key principle**: Separation of duties — the person who creates a financial record should not be the same person who approves it.

### 4. Encryption

- At rest: AES-256 via KMS (`alias/{workload}-sox-key`)
- In transit: TLS 1.3
- Re-encrypt at every zone boundary (Bronze → Silver → Gold)
- Financial data encryption is required for SOX IT controls

### 5. Audit Logging (SOX Section 302/404)

- Log ALL changes to financial data — every transformation, every value change
- CloudTrail enabled for all Lake Formation operations
- Audit log retention: **2555 days** (7 years — non-negotiable)
- Logs are immutable (append-only S3 with Object Lock)
- Required tracking:
  - Who made the change (user/agent ID)
  - What changed (before/after values for financial columns)
  - When (timestamp)
  - Why (transformation rule or manual override reason)
- Lineage must trace every financial number back to its source

### 6. Quality Rules (Higher Threshold)

SOX requires **higher quality thresholds** than default:

- Silver zone quality gate: **0.95** (default is 0.80)
- Gold zone quality gate: **0.99** (default is 0.95)
- Financial column accuracy: **100%** — no tolerance for incorrect financial values
- Anomaly detection: volume changes >20%, price changes >3 std dev
- All quality check results must be logged and retained for 7 years

### 7. Masking & Anonymization

SOX focuses less on masking and more on **integrity and auditability**:

| Column Type | Method | Rationale |
|------------|--------|-----------|
| manager_name, employee_name | No masking (needed for audit) | Audit trail requires attribution |
| Financial amounts | No masking (needed for audit) | Must be accurate and traceable |
| Account numbers | mask_partial in dashboards | `****1234` for executive views |

**Key difference from GDPR/HIPAA**: SOX often requires data to be **visible for audit**, not masked. Apply masking only for roles that don't need the detail.

### 8. LF-Tag Requirements

**Mandatory tagging:**

| Column Pattern | PII_Classification | PII_Type | Data_Sensitivity |
|---------------|-------------------|----------|-----------------|
| manager_name, employee_name | MEDIUM | NAME | MEDIUM |
| email (submitter) | MEDIUM | EMAIL | MEDIUM |
| account_number, iban | CRITICAL | FINANCIAL_ACCOUNT | CRITICAL |
| All financial measures (revenue, cost, profit) | NONE | — | LOW |
| All other columns | NONE | — | LOW |

**TBAC grants:**

```bash
# Auditor — full access, read-only (ALL sensitivity levels)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/AuditorRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# Finance Team — NONE + LOW + MEDIUM
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/FinanceRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# External Reviewer — NONE + LOW only
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/ExternalReviewerRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["LOW"]}]}}' \
  --permissions SELECT
```

### 9. SOX-Specific Requirements

**Bronze Zone Immutability (Critical for SOX):**
- Source financial records must NEVER be modified after ingestion
- Any code that attempts to update Bronze data is a SOX violation
- Bronze zone serves as the "original books and records"

**Change Tracking:**
- All transformations must produce lineage records
- Before/after values for financial columns must be logged
- Manual overrides require approval and justification (logged)

**Separation of Duties:**
- Pipeline creator ≠ pipeline approver
- Data engineer ≠ data auditor
- Transformation author ≠ quality reviewer

### 10. Config YAML

Merge into `config/quality_rules.yaml`:

```yaml
compliance:
  regulation: SOX
  financial_columns: [revenue, cost, profit, transaction_amount]
  change_tracking: enabled
  audit_retention_days: 2555
  quality_threshold: 0.99
  bronze_immutability: strict
  separation_of_duties: true
  encryption:
    at_rest: AES-256
    in_transit: TLS_1.3
    kms_key_alias: alias/${workload}-sox-key
  quality_rules:
    - rule: financial_accuracy
      columns: [revenue, cost, profit, transaction_amount]
      check: value_accuracy
      threshold: 1.0
      severity: critical
      description: "SOX requires 100% accuracy for financial values"
    - rule: silver_quality_gate
      check: overall_score
      threshold: 0.95
      severity: critical
      description: "SOX Silver zone requires 0.95+ quality score"
    - rule: gold_quality_gate
      check: overall_score
      threshold: 0.99
      severity: critical
      description: "SOX Gold zone requires 0.99+ quality score"
    - rule: volume_anomaly
      check: row_count_deviation
      threshold: 0.20
      severity: warning
      description: "Flag volume changes exceeding 20%"
    - rule: price_anomaly
      columns: [revenue, cost, profit]
      check: stddev_deviation
      threshold: 3.0
      severity: warning
      description: "Flag financial value changes exceeding 3 standard deviations"
    - rule: lineage_complete
      check: lineage_exists
      severity: critical
      description: "SOX requires complete data lineage for all financial records"
```

### 11. Verification

After deployment, verify controls are applied:

```bash
# 1. Verify Bronze zone is read-only (no write permissions for non-ingestion roles)
aws lakeformation list-permissions \
  --resource '{"Table": {"DatabaseName": "${DATABASE}", "Name": "bronze_${TABLE}"}}'

# 2. Verify LF-Tags applied
aws lakeformation get-resource-lf-tags \
  --resource '{"TableWithColumns": {"DatabaseName": "${DATABASE}", "Name": "${TABLE}", "ColumnNames": ["revenue", "manager_name"]}}'

# 3. Verify TBAC grants (External gets LOW only)
aws lakeformation list-permissions \
  --principal '{"DataLakePrincipalIdentifier": "arn:aws:iam::${ACCOUNT_ID}:role/ExternalReviewerRole"}'

# 4. Verify quality threshold is 0.95+
cat workloads/${WORKLOAD}/config/quality_rules.yaml | grep quality_threshold

# 5. Verify audit log retention (7 years)
aws s3api get-object-lock-configuration --bucket ${AUDIT_BUCKET}

# 6. Verify lineage exists for financial tables
ls workloads/${WORKLOAD}/output/lineage/*.json

# 7. Verify CloudTrail logging
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=lakeformation.amazonaws.com \
  --max-results 5
```

## Live Example

See `workloads/financial_portfolios/` for a working SOX-compliant pipeline:
- 7 Glue jobs (Bronze CSV → Silver Iceberg → Gold Iceberg star schema)
- 7 Iceberg tables in `financial_portfolios_db`
- Full lineage tracking
- Quality gates at 0.95+

## References

- `docs/governance-framework.md` lines 168-192 — SOX requirements and platform controls
- `workloads/financial_portfolios/config/quality_rules.yaml` — Live SOX quality config
- `shared/utils/pii_detection_and_tagging.py` — PII detection engine
- `shared/policies/guardrails/sec_003_pii_masking.cedar` — PII masking enforcement policy
