# Data Governance Framework

**Status:** ✅ Production-Ready
**Version:** 1.0
**Last Updated:** March 17, 2026

---

## Overview

The Agentic Data Onboarding platform includes a **built-in governance framework** that automatically applies PII detection, tag-based access control, and compliance controls to every workload. This is not optional — it's core infrastructure.

### Key Principles

1. **Governance by Default** — All workloads automatically scan for PII during onboarding
2. **Regulatory Compliance First** — Ask about GDPR, CCPA, HIPAA, SOX, PCI DSS requirements in Phase 1 discovery
3. **AI-Driven Detection** — Claude analyzes column names and content to identify sensitive data
4. **Column-Level Security** — Lake Formation LF-Tags enable fine-grained access control
5. **Audit Everything** — All access logged to CloudTrail for compliance reporting

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA ONBOARDING WORKFLOW                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Phase 1         │
                    │  Discovery       │◄─── Ask: GDPR? CCPA? HIPAA?
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Phase 3         │
                    │  Profiling       │
                    └────────┬─────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  PII DETECTION (Automatic)   │
              │  shared/utils/               │
              │  pii_detection_and_tagging.py│
              └──────────┬───────────────────┘
                         │
                         ├─► Name-based: email, phone, ssn, address, etc.
                         │
                         └─► Content-based: Regex on sample data (100 rows)
                             │
                             ▼
              ┌─────────────────────────────────┐
              │  LF-TAGS APPLIED                │
              │  - PII_Classification: CRITICAL │
              │  - PII_Type: EMAIL / PHONE      │
              │  - Data_Sensitivity: HIGH       │
              └──────────┬──────────────────────┘
                         │
                         ▼
              ┌─────────────────────────────────┐
              │  TAG-BASED ACCESS CONTROL       │
              │  Lake Formation Permissions     │
              │  - Analysts: LOW/MEDIUM only    │
              │  - Data Eng: ALL                │
              │  - QuickSight: MEDIUM/LOW only  │
              └──────────┬──────────────────────┘
                         │
                         ▼
              ┌─────────────────────────────────┐
              │  AUDIT LOGGING                  │
              │  CloudTrail + S3                │
              │  - Who accessed what column     │
              │  - When tags were applied       │
              │  - All LF permission changes    │
              └─────────────────────────────────┘
```

---

## Supported Regulations

### 1. GDPR (General Data Protection Regulation)

**Requirements:**
- Right to erasure (delete user data on request)
- Right to access (export user data)
- Data minimization (only collect what's needed)
- Consent tracking
- Data breach notification (72 hours)

**Platform Controls:**
- PII detection identifies personal data automatically
- LF-Tags enable column-level deletion (soft delete via status flag)
- Audit logs track all data access for breach investigation
- Retention policies auto-expire data after N days
- Quarantine tables isolate sensitive records

**Implementation:**
```yaml
# config/quality_rules.yaml
compliance:
  regulation: GDPR
  pii_retention_days: 365  # Auto-expire after 1 year
  consent_column: consent_given
  deletion_flag_column: is_deleted
  audit_retention_days: 2555  # 7 years
```

---

### 2. CCPA (California Consumer Privacy Act)

**Requirements:**
- Right to know what data is collected
- Right to delete
- Right to opt-out of data sales
- Privacy notice requirements

**Platform Controls:**
- Automatic PII inventory (all tagged columns reported)
- User deletion workflow via status flag
- Opt-out tracking in dimension tables
- Data lineage shows data provenance

**Implementation:**
```yaml
# config/quality_rules.yaml
compliance:
  regulation: CCPA
  pii_retention_days: 730  # 2 years default
  opt_out_column: ccpa_opt_out
  deletion_flag_column: is_deleted
  data_lineage_required: true
```

---

### 3. HIPAA (Health Insurance Portability and Accountability Act)

**Requirements:**
- PHI (Protected Health Information) must be encrypted
- Access controls and audit trails
- Breach notification
- Business Associate Agreements (BAAs)

**Platform Controls:**
- Zone-specific KMS encryption (re-encrypt at boundaries)
- Column-level access control via LF-Tags
- CloudTrail audit logs (immutable, 7-year retention)
- PHI detection patterns (name, DOB, SSN, address, medical IDs)

**Implementation:**
```yaml
# config/quality_rules.yaml
compliance:
  regulation: HIPAA
  phi_columns: [patient_name, dob, ssn, address, medical_record_number]
  encryption_required: true
  kms_key_alias: alias/hipaa-phi-key
  audit_retention_days: 2555  # 7 years
  access_logging: all_columns
```

---

### 4. SOX (Sarbanes-Oxley Act)

**Requirements:**
- Financial data integrity
- Audit trails for all changes
- Access controls
- Change management processes

**Platform Controls:**
- Immutable Bronze zone (source data never modified)
- All transformations logged with lineage
- Quality gates enforce data integrity
- Role-based access via Lake Formation

**Implementation:**
```yaml
# config/quality_rules.yaml
compliance:
  regulation: SOX
  financial_columns: [revenue, cost, profit, transaction_amount]
  change_tracking: enabled
  audit_retention_days: 2555  # 7 years
  quality_threshold: 0.99  # Higher threshold for financial data
```

---

### 5. PCI DSS (Payment Card Industry Data Security Standard)

**Requirements:**
- Cardholder data encryption
- Restricted access
- Security logging
- Quarterly security assessments

**Platform Controls:**
- Credit card detection (Luhn algorithm validation)
- Masking in logs and error messages (never log full card numbers)
- Encryption at rest (KMS) and in transit (TLS 1.3)
- Access limited to roles with PCI compliance training

**Implementation:**
```yaml
# config/quality_rules.yaml
compliance:
  regulation: PCI_DSS
  cardholder_data_columns: [card_number, cvv, expiry_date]
  masking: full  # Never store in cleartext
  encryption_required: true
  kms_key_alias: alias/pci-cardholder-key
  access_restricted_to: [pci_admin_role]
  audit_retention_days: 365
```

---

## PII Detection Framework

### Location

```
shared/utils/pii_detection_and_tagging.py
```

This is a **shared utility** — used by ALL workloads during onboarding.

### Detection Methods

#### 1. Name-Based Detection

Scans column names for PII patterns:

| Pattern | Examples | Sensitivity |
|---------|----------|-------------|
| `email` | email, user_email, contact_email | HIGH |
| `phone` | phone, mobile, telephone, phone_number | MEDIUM |
| `ssn` | ssn, social_security_number, national_id | CRITICAL |
| `address` | address, street, city, postal_code, zip | MEDIUM |
| `name` | name, first_name, last_name, full_name | HIGH |
| `dob` | dob, birth_date, date_of_birth | HIGH |
| `credit_card` | card_number, credit_card, payment_card | CRITICAL |
| `ip_address` | ip, ip_address, client_ip | LOW |
| `driver_license` | drivers_license, dl_number | HIGH |
| `passport` | passport, passport_number | CRITICAL |
| `financial` | account_number, iban, swift, routing_number | CRITICAL |

**Confidence:** 100% (column name matches pattern exactly)

#### 2. Content-Based Detection

Samples 100 rows and applies regex patterns:

| PII Type | Regex Pattern | Example Match |
|----------|---------------|---------------|
| EMAIL | `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z\|a-z]{2,}\b` | user@example.com |
| PHONE | `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b` | 555-123-4567 |
| SSN | `\b\d{3}-\d{2}-\d{4}\b` | 123-45-6789 |
| CREDIT_CARD | `\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b` | 4111-1111-1111-1111 |
| IP_ADDRESS | `\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b` | 192.168.1.1 |

**Confidence:** 90-95% (pattern match in sample data)

### Sensitivity Levels

| Level | Examples | Access Control |
|-------|----------|----------------|
| **CRITICAL** | SSN, credit cards, passport | Admin only |
| **HIGH** | Email, name, DOB, driver license | Data engineers + analysts with approval |
| **MEDIUM** | Phone, address | Analysts, dashboard users |
| **LOW** | IP address, user agent | All authenticated users |
| **NONE** | Business data (revenue, region, status) | All authenticated users |

### Lake Formation Tags Applied

Every PII column gets 3 tags:

```json
{
  "PII_Classification": "HIGH",       // CRITICAL / HIGH / MEDIUM / LOW / NONE
  "PII_Type": "EMAIL",                // EMAIL / PHONE / SSN / etc.
  "Data_Sensitivity": "HIGH"          // CRITICAL / HIGH / MEDIUM / LOW
}
```

---

## Tag-Based Access Control (TBAC)

### How It Works

Instead of granting users access to entire tables, grant access to **sensitivity levels**:

```python
# Grant analyst role access to LOW and MEDIUM sensitivity columns only
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT:role/AnalystRole" \
  --resource '{
    "LFTagPolicy": {
      "ResourceType": "COLUMN",
      "Expression": [{
        "TagKey": "Data_Sensitivity",
        "TagValues": ["LOW", "MEDIUM"]
      }]
    }
  }' \
  --permissions SELECT
```

### Access Patterns by Role

| Role | Sensitivity Access | Example Columns Visible |
|------|-------------------|------------------------|
| **Admin** | ALL | Everything |
| **Data Engineer** | ALL | Everything |
| **Analyst** | LOW, MEDIUM | phone, address, ip_address (NOT email, SSN) |
| **Dashboard User** | LOW | ip_address, device_type (NOT phone, email) |
| **ML Engineer** | LOW, MEDIUM (hashed) | Hashed versions of PII for joins |

### Column-Level Query Behavior

When a user queries a table with PII:

```sql
-- Analyst role (has access to LOW/MEDIUM only)
SELECT * FROM customer_data;

-- Returns:
-- customer_id, region, phone (visible), email (NULL - no access), ssn (NULL - no access)
```

Lake Formation **automatically filters columns** based on the user's tag permissions. No application code changes needed.

---

## MCP Integration for AI-Driven Governance

### Custom MCP Server

Location: `mcp-servers/pii-detection-server/`

**Purpose:** Enable Claude Code to manage PII governance via natural language.

### Available Tools

```bash
# Setup (one-time)
cd mcp-servers/pii-detection-server
./setup.sh
# Restart Claude Code
```

After setup, use natural language:

| User Request | Claude Action |
|--------------|---------------|
| "Detect PII in finsights_silver.funds_clean" | Runs `detect_pii_in_table`, applies LF-Tags |
| "Scan all tables in customer database for PII" | Runs `scan_database_for_pii`, tags all PII columns |
| "Show me all CRITICAL PII columns" | Runs `get_pii_columns` with filter |
| "Grant analyst-role access to LOW/MEDIUM data" | Runs `apply_column_security` with tag expression |
| "Generate PII compliance report" | Runs `get_pii_report` for audit |

### MCP Tools Reference

1. **detect_pii_in_table** — Scan single table
2. **scan_database_for_pii** — Scan entire database
3. **create_lf_tags** — Create the 3 LF-Tags
4. **get_pii_columns** — List tagged columns
5. **apply_column_security** — Grant tag-based permissions
6. **get_pii_report** — Generate compliance summary

---

## Integration into Onboarding Workflow

### When PII Detection Runs

| Phase | Action | Output |
|-------|--------|--------|
| **Phase 1: Discovery** | Ask about regulatory requirements (GDPR/CCPA/HIPAA) | Compliance controls configured |
| **Phase 3: Profiling** | Run name-based PII detection on all columns | PII columns flagged in `semantic.yaml` |
| **Phase 4: Build** | Generate masking rules for PII columns | Transformation scripts include hashing/masking |
| **Phase 5: Deploy** | Apply LF-Tags to Glue Catalog columns | Column-level permissions enforced |
| **Post-Staging Load** | (Optional) Content-based detection on flagged columns | Update LF-Tags if new PII found |

### Updated `semantic.yaml` Structure

```yaml
columns:
  identifiers:
    - name: email
      data_type: string
      classification: PII          # ← Added by PII detection
      pii_type: EMAIL              # ← Added by PII detection
      sensitivity: HIGH            # ← Added by PII detection
      confidence: 1.0              # ← Detection confidence
      pattern: email               # ← Matched pattern
      masking: hash                # ← Transformation rule
      lf_tag_applied: true         # ← LF-Tag status
      compliance: [GDPR, CCPA]     # ← Applicable regulations
```

---

## Access Control Patterns

### Pattern 1: Role-Based (Classic)

Grant users access to entire tables:

```bash
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::ACCOUNT:role/AnalystRole" \
  --resource '{"Table": {"DatabaseName": "customer_db", "Name": "orders"}}' \
  --permissions SELECT
```

**Problem:** Analysts see ALL columns, including SSNs and credit cards.

### Pattern 2: Tag-Based (Modern)

Grant users access to sensitivity levels:

```bash
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::ACCOUNT:role/AnalystRole" \
  --resource '{
    "LFTagPolicy": {
      "ResourceType": "COLUMN",
      "Expression": [{
        "TagKey": "Data_Sensitivity",
        "TagValues": ["LOW", "MEDIUM"]
      }]
    }
  }' \
  --permissions SELECT
```

**Benefit:** Analysts see phone/address (MEDIUM) but NOT email/SSN (HIGH/CRITICAL). Lake Formation filters automatically.

---

## Compliance Reporting

### PII Inventory Report

Generated via MCP or CLI:

```bash
python3 shared/utils/pii_detection_and_tagging.py \
  --database customer_db \
  --report
```

Output:

```json
{
  "database": "customer_db",
  "tables_with_pii": 5,
  "summary": {
    "critical": 12,  // SSN, credit cards, passport
    "high": 34,      // Email, name, DOB
    "medium": 18,    // Phone, address
    "low": 5         // IP address
  },
  "columns": [
    {
      "table": "customers",
      "column": "email",
      "pii_type": "EMAIL",
      "sensitivity": "HIGH",
      "lf_tag_applied": true,
      "access_granted_to": ["admin_role", "data_eng_role"]
    }
  ]
}
```

### Audit Log Queries

All Lake Formation operations logged to CloudTrail:

```sql
-- Who accessed PII columns in the last 7 days?
SELECT
  useridentity.principalid,
  eventname,
  requestparameters,
  eventtime
FROM cloudtrail_logs
WHERE eventname LIKE '%GetDataAccess%'
  AND eventtime >= CURRENT_DATE - INTERVAL '7' DAY
ORDER BY eventtime DESC;
```

---

## Best Practices

### 1. Always Ask About Compliance First

In Phase 1 discovery, BEFORE profiling:

> "Does this data need to comply with any regulatory frameworks? (GDPR, CCPA, HIPAA, SOX, PCI DSS)"

This determines:
- Retention policies
- Access controls
- Audit requirements
- Encryption standards

### 2. Review PII Detection Results

After profiling, present results to the human:

> "I detected 3 PII columns:
>   - `email` → HIGH sensitivity (pattern match: email addresses)
>   - `phone` → MEDIUM sensitivity (pattern match: phone numbers)
>   - `ssn` → CRITICAL sensitivity (name match: social security number)
>
> Confirm these are correct?"

Humans can override false positives.

### 3. Apply Least Privilege

Grant access to the MINIMUM sensitivity level needed:

- **Dashboards**: LOW only (aggregated metrics, no PII)
- **Analysts**: LOW + MEDIUM (phone/address for segmentation, no email/SSN)
- **Data Engineers**: ALL (need full access for transformations)
- **ML Engineers**: LOW + hashed MEDIUM/HIGH (for joins, not human-readable)

### 4. Log Everything

Enable CloudTrail for:
- Lake Formation `GetDataAccess` events (who accessed what)
- `AddLFTagsToResource` events (when tags were applied)
- `GrantPermissions` events (permission changes)

Retention: 7 years for HIPAA/SOX, 1 year for GDPR/CCPA minimum.

### 5. Test Tag Filtering

After granting permissions, test with a restricted role:

```bash
# Assume analyst role
aws sts assume-role --role-arn arn:aws:iam::ACCOUNT:role/AnalystRole --role-session-name test

# Query table
aws athena start-query-execution --query-string "SELECT * FROM customer_data"

# Verify: HIGH/CRITICAL columns return NULL
```

---

## Troubleshooting

### Issue: PII Detection Missed a Column

**Solution:** Manually add to `semantic.yaml`:

```yaml
columns:
  identifiers:
    - name: alternate_email
      classification: PII
      pii_type: EMAIL
      sensitivity: HIGH
      confidence: 1.0
      masking: hash
```

Re-run LF-Tag application:

```bash
python3 shared/utils/pii_detection_and_tagging.py \
  --database customer_db \
  --table customers \
  --apply-tags
```

### Issue: False Positive (Non-PII Flagged as PII)

**Solution:** Override in `semantic.yaml`:

```yaml
columns:
  dimensions:
    - name: email_domain  # Not PII, just a domain like "gmail.com"
      classification: NONE
      pii_type: null
      sensitivity: NONE
```

### Issue: User Can't See Column They Should Access

**Symptom:** Query returns NULL for a column the user should see.

**Root Cause:** Column has a sensitivity tag higher than the user's granted level.

**Solution:** Either:
1. Lower the column's sensitivity (if appropriate)
2. Grant the user access to the higher sensitivity level

```bash
# Option 2: Grant access to HIGH sensitivity
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::ACCOUNT:role/AnalystRole" \
  --resource '{
    "LFTagPolicy": {
      "ResourceType": "COLUMN",
      "Expression": [{
        "TagKey": "Data_Sensitivity",
        "TagValues": ["LOW", "MEDIUM", "HIGH"]
      }]
    }
  }' \
  --permissions SELECT
```

---

## Summary

The governance framework provides:

✅ **Automatic PII detection** — no manual column reviews
✅ **Regulatory compliance** — GDPR, CCPA, HIPAA, SOX, PCI DSS controls
✅ **Column-level security** — fine-grained access via Lake Formation tags
✅ **AI-driven management** — natural language governance via MCP
✅ **Audit trails** — CloudTrail logs for compliance reporting
✅ **Reusable across workloads** — shared utility, one-time setup

This is not optional. Every workload automatically gets governance as part of onboarding.

---

**Related Documentation:**
- `PII_DETECTION_AND_TAGGING.md` — Technical implementation details
- `MCP_PII_TAGGING_SOLUTION.md` — Lambda + MCP architecture options
- `mcp-servers/pii-detection-server/README.md` — MCP server usage guide
- `CLAUDE.md` — Project configuration (Security Rules section)
- `SKILLS.md` — Data Onboarding Agent Phase 1 Discovery (Section 6a-6d)
