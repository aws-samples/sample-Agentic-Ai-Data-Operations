# HIPAA Compliance Controls

> Use this prompt ONLY when HIPAA compliance is explicitly required.
> NOT applied by default — triggered when user selects HIPAA during discovery.

## When to Use

- User selects HIPAA during Phase 1 discovery
- User asks "does this comply with HIPAA?"
- Workload config has `compliance: [HIPAA]` in quality_rules.yaml
- Data contains Protected Health Information (PHI)

## Controls Applied

### 1. PHI Detection

Scan for all 12 PII types via `shared/utils/pii_detection_and_tagging.py`. HIPAA defines **18 PHI identifiers** — the platform detects these automatically:

| PII Type | HIPAA PHI Category | Sensitivity |
|----------|-------------------|-------------|
| NAME (patient_name) | Name | HIGH |
| EMAIL | Contact info | HIGH |
| PHONE | Telephone number | MEDIUM |
| ADDRESS (street, city, state, zip) | Geographic data | MEDIUM |
| DOB (date_of_birth) | Dates related to individual | HIGH |
| SSN | Social security number | CRITICAL |
| NATIONAL_ID (medical_record_number) | Medical record number | CRITICAL |
| IP_ADDRESS | Device identifiers | LOW |
| FINANCIAL_ACCOUNT (health_plan_id) | Health plan beneficiary number | CRITICAL |

**Additional PHI columns** (flag during discovery if present):
- Admission/discharge dates, visit dates
- Biometric identifiers (fingerprints, voice)
- Full-face photographs
- Any unique identifying number

### 2. Data Retention

- PHI audit logs: **2555 days** (7 years) — HIPAA minimum for audit trail
- PHI data retention: determined by state law (typically 6-10 years)
- Audit log retention is non-negotiable — cannot be shortened
- Expired PHI must be securely destroyed (not just deleted)

### 3. Access Control (Minimum Necessary Rule)

HIPAA's **minimum necessary standard** requires limiting PHI access to the minimum needed for the task:

| Role | Sensitivity Access | Justification |
|------|-------------------|---------------|
| Admin | ALL | System administration, compliance |
| Healthcare Provider | NONE + LOW + MEDIUM + HIGH | Patient care (NOT CRITICAL — no SSN) |
| Billing | NONE + LOW + MEDIUM + HIGH | Claims processing |
| Analyst | NONE + LOW + MEDIUM | Population health analytics (no individual PHI) |
| Dashboard User | NONE + LOW | Aggregated metrics only |

### 4. Encryption (Mandatory for PHI)

- At rest: AES-256 via KMS (`alias/hipaa-phi-key`) — **required, not optional**
- In transit: TLS 1.3 — **required, not optional**
- Re-encrypt at every zone boundary (Bronze → Silver → Gold)
- KMS key rotation: annual (automatic)
- Key alias: `alias/hipaa-phi-key` (dedicated key for PHI workloads)
- **PHI must never exist unencrypted** at any layer

### 5. Audit Logging (HIPAA Audit Trail)

- Log ALL access to PHI columns — no exceptions
- CloudTrail enabled for all Lake Formation operations
- Audit log retention: **2555 days** (7 years minimum)
- Logs are immutable (append-only S3 with Object Lock)
- Required events: `GetDataAccess`, `AddLFTagsToResource`, `GrantPermissions`, `RevokePermissions`
- Track: who accessed, what PHI, when, from where (IP), success/failure
- **Business Associate Agreements (BAAs)** must be in place for all third-party services

### 6. Quality Rules

Add to workload quality checks:

- All PHI columns must have LF-Tags applied
- Encryption must be verified on all PHI columns
- Access control grants must follow minimum necessary principle
- Audit logging must be active and writing to immutable storage
- PHI columns must not appear in error messages, logs, or debug output

### 7. Masking & Anonymization

| Column Type | Method | Example |
|------------|--------|---------|
| patient_name | hash (SHA-256) | `a1b2c3...` |
| email | mask_email | `j***@hospital.com` |
| phone | mask_partial | `555-***-4567` |
| address, city, state, zip | redact | `[REDACTED]` |
| dob | generalize | `1985-**-**` (year only) |
| ssn | hash (SHA-256) | `d4e5f6...` |
| medical_record_number | tokenize | `MRN-TOKEN-001` |

**De-identification**: For research/analytics, apply HIPAA Safe Harbor method — remove all 18 identifiers or use Expert Determination method.

### 8. LF-Tag Requirements

**All PHI columns MUST be tagged — no exceptions:**

| Column Pattern | PII_Classification | PII_Type | Data_Sensitivity |
|---------------|-------------------|----------|-----------------|
| ssn, social_security_number | CRITICAL | SSN | CRITICAL |
| medical_record_number, mrn | CRITICAL | NATIONAL_ID | CRITICAL |
| health_plan_id | CRITICAL | FINANCIAL_ACCOUNT | CRITICAL |
| patient_name, name | HIGH | NAME | HIGH |
| email | HIGH | EMAIL | HIGH |
| dob, date_of_birth | HIGH | DOB | HIGH |
| visit_date, admission_date | HIGH | DOB | HIGH |
| phone, mobile | MEDIUM | PHONE | MEDIUM |
| address, street | MEDIUM | ADDRESS | MEDIUM |
| city, state, zip | MEDIUM | ADDRESS | MEDIUM |
| All non-PHI columns | NONE | — | LOW |

**TBAC grants:**

```bash
# Admin — full access
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/HIPAAAdminRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# Healthcare Provider — HIGH + MEDIUM + LOW (NOT CRITICAL)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/ProviderRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["HIGH", "MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# Billing — HIGH + MEDIUM + LOW (NOT CRITICAL)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/BillingRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["HIGH", "MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# Analyst — MEDIUM + LOW only (no individual PHI)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/AnalystRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["MEDIUM", "LOW"]}]}}' \
  --permissions SELECT
```

### 9. HIPAA-Specific Requirements

**Business Associate Agreement (BAA):**
- AWS BAA must be in place (covers S3, Glue, Athena, Lake Formation, KMS, CloudTrail)
- Document in workload README that BAA is active

**Breach Notification:**
- If PHI breach detected: notify covered entity within 60 days
- Log breach details in audit trail immediately
- Reference incident response procedure in workload README

### 10. Config YAML

Merge into `config/quality_rules.yaml`:

```yaml
compliance:
  regulation: HIPAA
  phi_columns: [patient_name, dob, ssn, address, medical_record_number]
  encryption_required: true
  kms_key_alias: alias/hipaa-phi-key
  audit_retention_days: 2555
  access_logging: all_columns
  minimum_necessary: true
  baa_required: true
  breach_notification_days: 60
  encryption:
    at_rest: AES-256
    in_transit: TLS_1.3
    kms_key_alias: alias/hipaa-phi-key
  quality_rules:
    - rule: phi_columns_encrypted
      check: encryption_enabled
      columns: [patient_name, dob, ssn, address, medical_record_number]
      severity: critical
      description: "HIPAA requires all PHI to be encrypted at rest"
    - rule: phi_columns_tagged
      check: lf_tags_applied
      columns: [patient_name, dob, ssn, address, medical_record_number]
      severity: critical
      description: "All PHI columns must have LF-Tags for access control"
    - rule: audit_logging_active
      check: cloudtrail_enabled
      severity: critical
      description: "HIPAA requires audit trail for all PHI access"
    - rule: phi_not_in_logs
      check: no_pii_in_logs
      severity: critical
      description: "PHI must never appear in application logs or error messages"
```

### 11. Verification

After deployment, verify controls are applied:

```bash
# 1. Verify KMS encryption on S3 buckets
aws s3api get-bucket-encryption --bucket ${BUCKET}

# 2. Verify LF-Tags applied to all PHI columns
aws lakeformation get-resource-lf-tags \
  --resource '{"TableWithColumns": {"DatabaseName": "${DATABASE}", "Name": "${TABLE}", "ColumnNames": ["patient_name", "ssn", "dob"]}}'

# 3. Verify TBAC grants (Provider should NOT see CRITICAL)
aws lakeformation list-permissions \
  --principal '{"DataLakePrincipalIdentifier": "arn:aws:iam::${ACCOUNT_ID}:role/ProviderRole"}'

# 4. Test minimum necessary (Provider queries SSN — should return NULL)
aws athena start-query-execution \
  --query-string "SELECT ssn FROM ${DATABASE}.${TABLE} LIMIT 5" \
  --result-configuration "OutputLocation=s3://${BUCKET}/query-results/"

# 5. Verify CloudTrail logging active
aws cloudtrail get-trail-status --name ${TRAIL_NAME}

# 6. Verify audit log retention (S3 Object Lock)
aws s3api get-object-lock-configuration --bucket ${AUDIT_BUCKET}

# 7. Verify KMS key exists and rotation enabled
aws kms describe-key --key-id alias/hipaa-phi-key
aws kms get-key-rotation-status --key-id alias/hipaa-phi-key
```

## References

- `docs/governance-framework.md` lines 140-165 — HIPAA requirements and platform controls
- `demo/workflows/demo_governance_workflow.py` — HIPAA demo (20 patients, role-based access)
- `shared/utils/pii_detection_and_tagging.py` — PII/PHI detection engine
- `shared/policies/guardrails/sec_003_pii_masking.cedar` — PII masking enforcement policy
