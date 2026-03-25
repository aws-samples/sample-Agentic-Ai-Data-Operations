# CCPA Compliance Controls

> Use this prompt ONLY when CCPA compliance is explicitly required.
> NOT applied by default — triggered when user selects CCPA during discovery.

## When to Use

- User selects CCPA during Phase 1 discovery
- User asks "does this comply with CCPA?"
- Workload config has `compliance: [CCPA]` in quality_rules.yaml
- Data contains California consumer personal information

## Prerequisites

Before applying CCPA controls, verify these AWS resources exist:

| Resource | Check Command | What If Missing? |
|----------|---------------|------------------|
| **KMS key** `alias/{workload}-ccpa-key` | `aws kms describe-key --key-id alias/{workload}-ccpa-key --region us-east-1` | Run `prompts/environment-setup-agent/01-setup-aws-infrastructure.md` Step 4, or create manually: `aws kms create-key --description "CCPA personal information encryption key for {workload}"` then `aws kms create-alias --alias-name alias/{workload}-ccpa-key --target-key-id {KEY_ID}` |
| **IAM role** `PrivacyTeamRole` | `aws iam get-role --role-name PrivacyTeamRole` | Create with trust policy for Lake Formation and Glue: `aws iam create-role --role-name PrivacyTeamRole --assume-role-policy-document file://trust-policy.json` |
| **IAM role** `MarketingRole` | `aws iam get-role --role-name MarketingRole` | Create with trust policy for Lake Formation |
| **IAM role** `ConsumerRequestRole` | `aws iam get-role --role-name ConsumerRequestRole` | Create with trust policy for handling consumer data requests (access, deletion) |
| **IAM role** `DashboardUserRole` | `aws iam get-role --role-name DashboardUserRole` | Create with trust policy for QuickSight and Athena |
| **LF-Tag** `PII_Classification` | `aws lakeformation list-lf-tags --region us-east-1 \| grep PII_Classification` | Run `prompts/environment-setup-agent/01-setup-aws-infrastructure.md` Step 6, or create manually: `aws lakeformation create-lf-tag --tag-key PII_Classification --tag-values CRITICAL,HIGH,MEDIUM,LOW,NONE` |
| **LF-Tag** `PII_Type` | `aws lakeformation list-lf-tags --region us-east-1 \| grep PII_Type` | Create: `aws lakeformation create-lf-tag --tag-key PII_Type --tag-values SSN,EMAIL,PHONE,ADDRESS,DOB,NATIONAL_ID,NAME,FINANCIAL_ACCOUNT,DRIVER_LICENSE` |
| **LF-Tag** `Data_Sensitivity` | `aws lakeformation list-lf-tags --region us-east-1 \| grep Data_Sensitivity` | Create: `aws lakeformation create-lf-tag --tag-key Data_Sensitivity --tag-values CRITICAL,HIGH,MEDIUM,LOW` |
| **CloudTrail** enabled | `aws cloudtrail get-trail-status --name {TRAIL} --region us-east-1` | Enable CloudTrail in AWS Console or via CLI. CCPA requires audit trail for all personal information access. |
| **S3 audit bucket** with Object Lock | `aws s3api get-object-lock-configuration --bucket {AUDIT_BUCKET}` | Create immutable audit bucket: `aws s3api create-bucket --bucket {AUDIT_BUCKET} --object-lock-enabled-for-bucket --region us-east-1` |

**Quick check** (run this before applying CCPA controls):
```bash
# Check if key exists (replace {workload} with your workload name)
aws kms describe-key --key-id alias/{workload}-ccpa-key --region us-east-1 && echo "✓ KMS key exists" || echo "✗ KMS key missing"

# Check if roles exist
for ROLE in PrivacyTeamRole MarketingRole ConsumerRequestRole DashboardUserRole; do
  aws iam get-role --role-name $ROLE >/dev/null 2>&1 && echo "✓ $ROLE exists" || echo "✗ $ROLE missing"
done

# Check if LF-Tags exist
aws lakeformation list-lf-tags --region us-east-1 --query 'LFTags[].TagKey' --output text | grep -E 'PII_Classification|PII_Type|Data_Sensitivity' && echo "✓ LF-Tags exist" || echo "✗ LF-Tags missing"
```

**If prerequisites are missing**: Run the environment setup first (`prompts/environment-setup-agent/01-setup-aws-infrastructure.md`) or create resources manually using the commands above. Do NOT proceed with CCPA onboarding until all prerequisites pass.

## Controls Applied

### 1. PII Detection

Scan for all 12 PII types via `shared/utils/pii_detection_and_tagging.py`. CCPA-relevant subset:

| PII Type | CCPA Category | Sensitivity |
|----------|--------------|-------------|
| NAME | Identifier | HIGH |
| EMAIL | Identifier | HIGH |
| PHONE | Identifier | MEDIUM |
| ADDRESS | Identifier | MEDIUM |
| DOB | Identifier | MEDIUM |
| SSN | Identifier | CRITICAL |
| FINANCIAL_ACCOUNT | Financial info | CRITICAL |
| IP_ADDRESS | Online identifier | LOW |
| DRIVER_LICENSE | Identifier | HIGH |

### 2. Data Retention

- Default: **730 days** (2 years) for personal information
- Audit logs: **2555 days** (7 years)
- Implement automated expiration via Glue lifecycle rules or S3 lifecycle policies
- Deletion requests must be processed within 45 days

### 3. Access Control

| Role | Sensitivity Access | Purpose |
|------|-------------------|---------|
| Privacy Team | ALL | Compliance, deletion requests |
| Data Engineer | ALL | Pipeline maintenance |
| Marketing | NONE + LOW | Aggregated analytics only |
| Dashboard User | NONE + LOW | Aggregated views only |

### 4. Encryption

- At rest: AES-256 via KMS (`alias/{workload}-ccpa-key`)
- In transit: TLS 1.3
- Re-encrypt at every zone boundary (Bronze → Silver → Gold)

### 5. Audit Logging

- Log ALL access to personal information columns
- CloudTrail enabled for Lake Formation operations
- Audit log retention: 2555 days (7 years)
- Track all deletion requests and their fulfillment
- Required CloudTrail events: `GetDataAccess`, `AddLFTagsToResource`, `GrantPermissions`

### 6. Quality Rules

Add to workload quality checks:

- `ccpa_opt_out` column must exist (for right to opt-out)
- `is_deleted` column must exist (for right to delete)
- Data lineage must be complete for all personal information (right to know)
- PII columns must have LF-Tags applied (verified post-deploy)
- Retention check: flag records older than `pii_retention_days`

### 7. Masking & Anonymization

| Column Type | Method | Example |
|------------|--------|---------|
| EMAIL | mask_email | `j***@example.com` |
| NAME | mask_partial | `John S****` |
| PHONE | mask_partial | `555-***-4567` |
| ADDRESS | redact | `[REDACTED]` |
| SSN | hash (SHA-256) | `a1b2c3...` |
| FINANCIAL_ACCOUNT | mask_partial | `****1234` |

Masking applies in Silver and Gold zones. Bronze retains raw data (immutable, access-restricted).

### 8. LF-Tag Requirements

**Mandatory tagging for all personal information columns:**

| Column Pattern | PII_Classification | PII_Type | Data_Sensitivity |
|---------------|-------------------|----------|-----------------|
| name, first_name, last_name | HIGH | NAME | HIGH |
| email, user_email | HIGH | EMAIL | HIGH |
| phone, mobile | MEDIUM | PHONE | MEDIUM |
| address, street, city, zip | MEDIUM | ADDRESS | MEDIUM |
| dob, date_of_birth | MEDIUM | DOB | MEDIUM |
| ssn | CRITICAL | SSN | CRITICAL |
| account_number, iban | CRITICAL | FINANCIAL_ACCOUNT | CRITICAL |
| ip_address, client_ip | LOW | IP_ADDRESS | LOW |
| All non-PII columns | NONE | — | LOW |

**TBAC grants:**

```bash
# Privacy Team — full access (all sensitivity levels)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/PrivacyTeamRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# Marketing — NONE + LOW only
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/MarketingRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["LOW"]}]}}' \
  --permissions SELECT
```

### 9. CCPA-Specific Columns

The following columns must be added to Silver/Gold tables when CCPA applies:

| Column | Type | Purpose |
|--------|------|---------|
| `ccpa_opt_out` | BOOLEAN | Tracks consumer opt-out of data sale |
| `opt_out_timestamp` | TIMESTAMP | When opt-out was recorded |
| `is_deleted` | BOOLEAN | Soft delete flag for right to delete |
| `deletion_requested_at` | TIMESTAMP | When deletion was requested |
| `data_source` | STRING | Where this data was collected (right to know) |

### 10. Config YAML

Merge into `config/quality_rules.yaml`:

```yaml
compliance:
  regulation: CCPA
  pii_retention_days: 730
  opt_out_column: ccpa_opt_out
  deletion_flag_column: is_deleted
  data_lineage_required: true
  deletion_deadline_days: 45
  audit_retention_days: 2555
  encryption:
    at_rest: AES-256
    in_transit: TLS_1.3
    kms_key_alias: alias/${workload}-ccpa-key
  quality_rules:
    - rule: opt_out_column_exists
      column: ccpa_opt_out
      check: column_exists
      severity: critical
      description: "CCPA requires opt-out tracking for data sale"
    - rule: deletion_flag_exists
      column: is_deleted
      check: column_exists
      severity: critical
      description: "CCPA right to delete requires soft delete capability"
    - rule: lineage_complete
      check: lineage_exists
      severity: critical
      description: "CCPA right to know requires complete data lineage"
    - rule: pii_retention_check
      check: max_age_days
      threshold: 730
      severity: warning
      description: "Flag records exceeding CCPA retention period"
```

### 11. Verification

After deployment, verify controls are applied:

```bash
# 1. Verify LF-Tags exist
aws lakeformation list-lf-tags --max-results 10

# 2. Verify tags applied to PII columns
aws lakeformation get-resource-lf-tags \
  --resource '{"TableWithColumns": {"DatabaseName": "${DATABASE}", "Name": "${TABLE}", "ColumnNames": ["email", "name"]}}'

# 3. Verify TBAC grants (marketing gets LOW only)
aws lakeformation list-permissions \
  --principal '{"DataLakePrincipalIdentifier": "arn:aws:iam::${ACCOUNT_ID}:role/MarketingRole"}'

# 4. Verify opt-out column exists
aws athena start-query-execution \
  --query-string "DESCRIBE ${DATABASE}.${TABLE}" \
  --result-configuration "OutputLocation=s3://${BUCKET}/query-results/"

# 5. Verify data lineage is recorded
ls workloads/${WORKLOAD}/output/lineage/*.json

# 6. Verify CloudTrail logging
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=lakeformation.amazonaws.com \
  --max-results 5
```

## References

- `docs/governance-framework.md` lines 113-137 — CCPA requirements and platform controls
- `docs/governance-integration-example.md` — End-to-end GDPR+CCPA onboarding example
- `shared/utils/pii_detection_and_tagging.py` — PII detection engine
- `shared/policies/guardrails/sec_003_pii_masking.cedar` — PII masking enforcement policy
