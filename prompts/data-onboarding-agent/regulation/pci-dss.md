# PCI DSS Compliance Controls

> Use this prompt ONLY when PCI DSS compliance is explicitly required.
> NOT applied by default — triggered when user selects PCI DSS during discovery.

## When to Use

- User selects PCI DSS during Phase 1 discovery
- User asks "does this comply with PCI DSS?"
- Workload config has `compliance: [PCI_DSS]` in quality_rules.yaml
- Data contains cardholder data (card numbers, CVV, expiry dates)

## Controls Applied

### 1. PII Detection (Cardholder Data)

Scan via `shared/utils/pii_detection_and_tagging.py`. PCI DSS scope is narrow — focused on **cardholder data**:

| PII Type | PCI DSS Category | Sensitivity |
|----------|-----------------|-------------|
| CREDIT_CARD (card_number) | Primary Account Number (PAN) | CRITICAL |
| CVV (cvv, cvc, security_code) | Sensitive Authentication Data | CRITICAL |
| Expiry date (expiry_date, exp_date) | Cardholder data | HIGH |
| NAME (cardholder_name) | Cardholder data | HIGH |
| ADDRESS (billing_address, billing_zip) | Cardholder data | MEDIUM |

**Detection includes Luhn algorithm validation** for card numbers (not just pattern matching).

**CRITICAL RULE: card_number and cvv must NEVER appear in Gold zone unmasked.** Transformation scripts must hash or tokenize these columns before promotion to Silver/Gold.

### 2. Data Retention

- Cardholder data: **minimum necessary** — delete as soon as business need expires
- CVV/CVC: **NEVER stored** after authorization — must be excluded from pipeline entirely
- Audit logs: **365 days** minimum (PCI DSS Requirement 10.7)
- Implement automated expiration via S3 lifecycle policies

### 3. Access Control (Restricted)

PCI DSS requires the **strictest access controls** of all regulations:

| Role | Sensitivity Access | Purpose |
|------|-------------------|---------|
| PCI Admin (`pci_admin_role`) | ALL including CRITICAL | Cardholder data management |
| Payment Processing | HIGH + MEDIUM + LOW | Transaction processing (no raw PAN) |
| Analyst | NONE + LOW | Aggregated payment analytics |
| Dashboard User | NONE + LOW | Revenue reporting (no card data) |

**ONLY `pci_admin_role` can access CRITICAL columns.** No exceptions.

### 4. Encryption (PCI DSS Requirement 3)

- At rest: AES-256 via KMS (`alias/pci-cardholder-key`) — **dedicated key for cardholder data**
- In transit: TLS 1.3 (PCI DSS Requirement 4)
- Re-encrypt at every zone boundary (Bronze → Silver → Gold)
- KMS key rotation: annual (automatic)
- **PAN must be rendered unreadable anywhere it is stored** (Requirement 3.4)
- Acceptable methods: one-way hash, truncation, index tokens, strong cryptography

### 5. Audit Logging (PCI DSS Requirement 10)

- Log ALL access to cardholder data — every query, every transformation
- CloudTrail enabled for Lake Formation operations
- Audit log retention: **365 days** minimum
- Logs are immutable (append-only)
- Required tracking:
  - All access to cardholder data (Req 10.2.1)
  - All actions by admin/root (Req 10.2.2)
  - Access to audit trails (Req 10.2.3)
  - Invalid logical access attempts (Req 10.2.4)
  - Changes to identification/authentication (Req 10.2.5)

### 6. Quality Rules

Add to workload quality checks:

- card_number must pass Luhn validation
- CVV must NOT exist in Silver or Gold zones (must be dropped in Bronze → Silver)
- card_number must be hashed/tokenized in Silver and Gold
- No cardholder data in error messages, logs, or debug output
- PCI columns must have LF-Tags applied

### 7. Masking & Anonymization

| Column Type | Method | Result | Notes |
|------------|--------|--------|-------|
| card_number | tokenize | `tok_a1b2c3d4` | One-way token, original never recoverable |
| card_number (display) | mask_pan | `****-****-****-1234` | Last 4 digits only (Req 3.3) |
| cvv | **DROP** | Column removed entirely | NEVER store after authorization |
| expiry_date | hash (SHA-256) | `e5f6a7...` | Or drop if not needed |
| cardholder_name | mask_partial | `John S****` | If needed; prefer dropping |
| billing_address | redact | `[REDACTED]` | Unless needed for fraud detection |

**Bronze → Silver transformation MUST:**
1. Drop CVV column entirely
2. Tokenize or hash card_number
3. Log the transformation (what was masked, row count)

### 8. LF-Tag Requirements

**Strictest tagging of all regulations:**

| Column Pattern | PII_Classification | PII_Type | Data_Sensitivity |
|---------------|-------------------|----------|-----------------|
| card_number, credit_card, pan | CRITICAL | CREDIT_CARD | CRITICAL |
| cvv, cvc, security_code | CRITICAL | CREDIT_CARD | CRITICAL |
| expiry_date, exp_date | HIGH | CREDIT_CARD | HIGH |
| cardholder_name | HIGH | NAME | HIGH |
| billing_address, billing_zip | MEDIUM | ADDRESS | MEDIUM |
| All non-cardholder columns | NONE | — | LOW |

**TBAC grants:**

```bash
# PCI Admin — ONLY role with CRITICAL access
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/pci_admin_role" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# Payment Processing — HIGH + MEDIUM + LOW (no raw PAN)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/PaymentProcessingRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["HIGH", "MEDIUM", "LOW"]}]}}' \
  --permissions SELECT

# Analyst — NONE + LOW only (no cardholder data at all)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::${ACCOUNT_ID}:role/AnalystRole" \
  --resource '{"LFTagPolicy": {"ResourceType": "COLUMN", "Expression": [{"TagKey": "Data_Sensitivity", "TagValues": ["LOW"]}]}}' \
  --permissions SELECT
```

### 9. PCI DSS-Specific Requirements

**Cardholder Data Environment (CDE):**
- The S3 bucket/path storing cardholder data is part of the CDE
- CDE must be documented in workload README
- Network segmentation: cardholder data S3 paths should use VPC endpoints

**Quarterly Assessments:**
- Run PII detection scan quarterly (not just at onboarding)
- Verify LF-Tags are still correctly applied
- Review access grants — remove any unnecessary permissions
- Document results in workload README

**Incident Response:**
- If cardholder data breach detected: initiate incident response immediately
- Preserve all audit logs
- Reference PCI DSS Requirement 12.10 (Incident Response Plan)

### 10. Config YAML

Merge into `config/quality_rules.yaml`:

```yaml
compliance:
  regulation: PCI_DSS
  cardholder_data_columns: [card_number, cvv, expiry_date]
  masking: full
  encryption_required: true
  kms_key_alias: alias/pci-cardholder-key
  access_restricted_to: [pci_admin_role]
  audit_retention_days: 365
  cvv_policy: drop_after_auth
  pan_rendering: tokenize
  encryption:
    at_rest: AES-256
    in_transit: TLS_1.3
    kms_key_alias: alias/pci-cardholder-key
  quality_rules:
    - rule: luhn_validation
      column: card_number
      check: luhn_check
      severity: critical
      description: "Card numbers must pass Luhn algorithm validation"
    - rule: cvv_not_in_silver
      column: cvv
      check: column_not_exists
      zone: silver
      severity: critical
      description: "CVV must NEVER exist in Silver or Gold zones"
    - rule: cvv_not_in_gold
      column: cvv
      check: column_not_exists
      zone: gold
      severity: critical
      description: "CVV must NEVER exist in Silver or Gold zones"
    - rule: pan_tokenized_silver
      column: card_number
      check: is_tokenized
      zone: silver
      severity: critical
      description: "PAN must be tokenized/hashed in Silver zone"
    - rule: pan_tokenized_gold
      column: card_number
      check: is_tokenized
      zone: gold
      severity: critical
      description: "PAN must be tokenized/hashed in Gold zone"
    - rule: no_cardholder_in_logs
      check: no_pii_in_logs
      columns: [card_number, cvv, expiry_date]
      severity: critical
      description: "Cardholder data must never appear in logs or error messages"
```

### 11. Verification

After deployment, verify controls are applied:

```bash
# 1. Verify KMS encryption with dedicated PCI key
aws kms describe-key --key-id alias/pci-cardholder-key
aws kms get-key-rotation-status --key-id alias/pci-cardholder-key

# 2. Verify LF-Tags applied to cardholder columns
aws lakeformation get-resource-lf-tags \
  --resource '{"TableWithColumns": {"DatabaseName": "${DATABASE}", "Name": "${TABLE}", "ColumnNames": ["card_number", "expiry_date"]}}'

# 3. Verify ONLY pci_admin_role has CRITICAL access
aws lakeformation list-permissions \
  --principal '{"DataLakePrincipalIdentifier": "arn:aws:iam::${ACCOUNT_ID}:role/pci_admin_role"}'

# 4. Verify CVV column does NOT exist in Silver/Gold
aws athena start-query-execution \
  --query-string "DESCRIBE ${DATABASE}.silver_${TABLE}" \
  --result-configuration "OutputLocation=s3://${BUCKET}/query-results/"
# Expected: cvv column should NOT appear

# 5. Verify card_number is tokenized in Silver/Gold
aws athena start-query-execution \
  --query-string "SELECT card_number FROM ${DATABASE}.silver_${TABLE} LIMIT 5" \
  --result-configuration "OutputLocation=s3://${BUCKET}/query-results/"
# Expected: tokenized values (tok_xxx), NOT raw card numbers

# 6. Verify Analyst cannot see cardholder data
aws lakeformation list-permissions \
  --principal '{"DataLakePrincipalIdentifier": "arn:aws:iam::${ACCOUNT_ID}:role/AnalystRole"}'
# Expected: only LOW sensitivity access

# 7. Verify CloudTrail logging
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=lakeformation.amazonaws.com \
  --max-results 5
```

## References

- `docs/governance-framework.md` lines 195-221 — PCI DSS requirements and platform controls
- `shared/utils/pii_detection_and_tagging.py` — PII detection engine (includes Luhn validation)
- `shared/policies/guardrails/sec_003_pii_masking.cedar` — PII masking enforcement policy
