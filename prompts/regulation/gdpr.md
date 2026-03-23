# GDPR Compliance Controls

> Use this prompt ONLY when GDPR compliance is explicitly required.
> NOT applied by default — triggered when user selects GDPR during discovery.

## When to Use

- User selects GDPR during Phase 1 discovery
- User asks "does this comply with GDPR?"
- Workload config has `compliance: [GDPR]` in quality_rules.yaml
- Data contains EU/EEA personal data

## Controls Applied

### 1. PII Detection

Scan for all 12 PII types via `shared/utils/pii_detection_and_tagging.py`. GDPR-relevant subset:

| PII Type | GDPR Category | Sensitivity |
|----------|--------------|-------------|
| NAME | Personal data | HIGH |
| EMAIL | Personal data | HIGH |
| PHONE | Personal data | MEDIUM |
| ADDRESS | Personal data | MEDIUM |
| DOB | Personal data | MEDIUM |
| SSN / NATIONAL_ID | Special category | CRITICAL |
| IP_ADDRESS | Personal data (online identifier) | LOW |
| PASSPORT | Personal data | CRITICAL |
| DRIVER_LICENSE | Personal data | HIGH |
| FINANCIAL_ACCOUNT | Personal data | CRITICAL |

### 2. Data Retention

- Default: **365 days** for PII columns (configurable per workload)
- Audit logs: **2555 days** (7 years)
- Implement automated expiration via Glue lifecycle rules or S3 lifecycle policies
- Expired data must be permanently deleted, not just archived

### 3. Access Control

| Role | Sensitivity Access | Purpose |
|------|-------------------|---------|
| Data Protection Officer (DPO) | ALL | Compliance oversight |
| Data Steward | NONE + LOW + MEDIUM | Data quality management |
| Analyst | NONE + LOW | Reporting on non-PII only |
| Dashboard User | NONE + LOW | Aggregated views only |

### 4. Encryption

- At rest: AES-256 via KMS (`alias/{workload}-gdpr-key`)
- In transit: TLS 1.3
- Re-encrypt at every zone boundary (Bronze → Silver → Gold)
- KMS key rotation: annual (automatic)

### 5. Audit Logging

- Log ALL access to PII columns (who, what, when, where)
- CloudTrail enabled for Lake Formation operations
- Audit log retention: 2555 days (7 years)
- Logs are immutable (append-only S3 with Object Lock)
- Required CloudTrail events: `GetDataAccess`, `AddLFTagsToResource`, `GrantPermissions`, `RevokePermissions`

### 6. Quality Rules

Add to workload quality checks:

- `consent_given` column must not be null for any active record
- `is_deleted` column must exist (for right to erasure)
- PII columns must have LF-Tags applied (verified post-deploy)
- Data retention check: flag records older than `pii_retention_days`

### 7. Masking & Anonymization

| Column Type | Method | Example |
|------------|--------|---------|
| EMAIL | mask_email | `j***@example.com` |
| NAME | mask_partial | `John S****` |
| PHONE | mask_partial | `555-***-4567` |
| ADDRESS | redact | `[REDACTED]` |
| SSN / NATIONAL_ID | hash (SHA-256) | `a1b2c3...` |
| IP_ADDRESS | truncate | `192.168.x.x` |

Masking applies in Silver and Gold zones. Bronze retains raw data (immutable, access-restricted).

### 8. LF-Tag Requirements

**Mandatory tagging for all personal data columns:**

| Column Pattern | PII_Classification | PII_Type | Data_Sensitivity |
|---------------|-------------------|----------|-----------------|
| name, first_name, last_name | HIGH | NAME | HIGH |
| email, user_email | HIGH | EMAIL | HIGH |
| phone, mobile, telephone | MEDIUM | PHONE | MEDIUM |
| address, street, city, zip | MEDIUM | ADDRESS | MEDIUM |
| dob, date_of_birth | MEDIUM | DOB | MEDIUM |
| ssn, national_id | CRITICAL | SSN | CRITICAL |
| passport, passport_number | CRITICAL | PASSPORT | CRITICAL |
| ip_address, client_ip | LOW | IP_ADDRESS | LOW |
| All non-PII columns | NONE | — | LOW |

**TBAC grants:**

```bash
# DPO — full access (all sensitivity levels)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/DPORole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# Data Steward — NONE + LOW + MEDIUM
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/DataStewardRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["LOW", "MEDIUM"]}]}}' \
  --permissions SELECT

# Analyst — NONE + LOW only
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/AnalystRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["LOW"]}]}}' \
  --permissions SELECT
```

### 9. GDPR-Specific Columns

The following columns must be added to Silver/Gold tables when GDPR applies:

| Column | Type | Purpose |
|--------|------|---------|
| `consent_given` | BOOLEAN | Tracks data subject consent |
| `consent_timestamp` | TIMESTAMP | When consent was given/withdrawn |
| `is_deleted` | BOOLEAN | Soft delete flag for right to erasure |
| `deletion_requested_at` | TIMESTAMP | When erasure was requested |
| `data_subject_id` | STRING | Links records to a data subject for export/deletion |

### 10. Config YAML

Merge into `config/quality_rules.yaml`:

```yaml
compliance:
  regulation: GDPR
  pii_retention_days: 365
  consent_column: consent_given
  deletion_flag_column: is_deleted
  audit_retention_days: 2555
  data_minimization: true
  breach_notification_hours: 72
  right_to_erasure: soft_delete
  right_to_access: lineage_export
  encryption:
    at_rest: AES-256
    in_transit: TLS_1.3
    kms_key_alias: alias/${workload}-gdpr-key
  quality_rules:
    - rule: consent_not_null
      column: consent_given
      check: not_null
      severity: critical
      description: "GDPR requires consent tracking for all active records"
    - rule: deletion_flag_exists
      column: is_deleted
      check: column_exists
      severity: critical
      description: "GDPR right to erasure requires soft delete capability"
    - rule: pii_retention_check
      check: max_age_days
      threshold: 365
      severity: warning
      description: "Flag records exceeding GDPR retention period"
```

### 11. Verification

After deployment, verify controls are applied:

```bash
# 1. Verify LF-Tags exist
aws lakeformation list-lf-tags --max-results 10

# 2. Verify tags applied to PII columns
aws lakeformation get-resource-lf-tags \
  --resource '{"TableWithColumns": {"DatabaseName": "${DATABASE}", "Name": "${TABLE}", "ColumnNames": ["email", "name"]}}'

# 3. Verify TBAC grants
aws lakeformation list-permissions \
  --principal '{"DataLakePrincipalIdentifier": "arn:aws:iam::${ACCOUNT_ID}:role/AnalystRole"}'

# 4. Test column filtering (assume restricted role, query table)
aws athena start-query-execution \
  --query-string "SELECT email, name FROM ${DATABASE}.${TABLE} LIMIT 5" \
  --result-configuration "OutputLocation=s3://${BUCKET}/query-results/"
# Expected: email and name return NULL for Analyst role

# 5. Verify consent column exists
aws athena start-query-execution \
  --query-string "DESCRIBE ${DATABASE}.${TABLE}" \
  --result-configuration "OutputLocation=s3://${BUCKET}/query-results/"

# 6. Verify CloudTrail logging
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=lakeformation.amazonaws.com \
  --max-results 5
```

## References

- `docs/governance-framework.md` lines 84-110 — GDPR requirements and platform controls
- `docs/governance-integration-example.md` lines 69-76 — GDPR+CCPA onboarding example
- `shared/utils/pii_detection_and_tagging.py` — PII detection engine
- `shared/policies/guardrails/sec_003_pii_masking.cedar` — PII masking enforcement policy
