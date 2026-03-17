# Governance Integration Example

**How the PII Detection Framework Integrates into Standard Onboarding**

---

## Standard Onboarding Prompt (BEFORE)

```
Onboard new dataset: customer_data

Source:
- Location: s3://customer-bucket/data.csv
- Format: CSV

Schema:
- customer_id: INT
- name: STRING
- email: STRING
- revenue: DECIMAL

Data Zones:
- Landing → Staging → Publish

Quality threshold: 95%
```

**Problem:** No mention of PII, no regulatory compliance, no access control.

---

## Enhanced Onboarding Prompt (AFTER)

```
Onboard new dataset: customer_data

Source:
- Location: s3://customer-bucket/data.csv
- Format: CSV

Compliance & Governance:
- Regulatory requirements: GDPR, CCPA
- PII detection: Automatic via shared/utils/pii_detection_and_tagging.py
- Tag-based access control: Analysts → LOW/MEDIUM only
- Audit logging: CloudTrail for all Lake Formation operations

Schema:
- customer_id: INT
- name: STRING (PII expected)
- email: STRING (PII expected)
- revenue: DECIMAL

Data Zones:
- Landing → Staging (with PII masking) → Publish

Quality threshold: 95%
```

**Result:** Governance controls applied automatically during onboarding.

---

## What Happens During Onboarding

### Phase 1: Discovery

Claude asks:

> "Does this data comply with any regulations?"
> - ☑ GDPR
> - ☑ CCPA
> - ☐ HIPAA
> - ☐ SOX
> - ☐ PCI DSS

User confirms: **GDPR + CCPA**

Claude applies controls:
- Right to erasure (soft delete flag)
- PII detection required
- Column-level access control
- 365-day retention policy
- Audit logging (CloudTrail)

### Phase 3: Profiling + PII Detection

Claude runs `shared/utils/pii_detection_and_tagging.py`:

```
🔍 Detecting PII in customer_data...

Results:
  ✓ name → HIGH (NAME pattern matched)
  ✓ email → HIGH (EMAIL pattern matched)
  ✓ customer_id → NONE (not PII)
  ✓ revenue → NONE (not PII)

Summary:
  • 2 PII columns detected
  • 2 non-PII columns
```

Claude presents to user:

> "I detected 2 PII columns:
>   - `name` → HIGH sensitivity (person name)
>   - `email` → HIGH sensitivity (email address)
>
> For GDPR/CCPA compliance, these will be:
>   - Masked in Staging (partial redaction)
>   - Tagged with LF-Tags for column-level access
>   - Logged in CloudTrail (all access tracked)
>
> Confirm?"

User: "Yes"

### Phase 4: Build Pipeline

Claude generates transformation scripts with PII masking:

**scripts/transform/landing_to_staging.py:**
```python
# PII masking rules (auto-generated)
df['name'] = df['name'].apply(mask_partial)  # John S****
df['email'] = df['email'].apply(mask_email)  # j***@email.com

# Log all PII transformations
logger.info(f"Masked {len(df)} rows: name, email")
```

**config/semantic.yaml:**
```yaml
columns:
  identifiers:
    - name: name
      data_type: string
      classification: PII          # ← Added by PII detection
      pii_type: NAME
      sensitivity: HIGH
      masking: mask_partial
      lf_tag_applied: true
      compliance: [GDPR, CCPA]

    - name: email
      data_type: string
      classification: PII
      pii_type: EMAIL
      sensitivity: HIGH
      masking: mask_email
      lf_tag_applied: true
      compliance: [GDPR, CCPA]
```

### Phase 5: Deploy

Claude applies Lake Formation tags:

```bash
# Via MCP or AWS CLI
aws lakeformation add-lf-tags-to-resource \
  --resource '{"TableWithColumns": {
    "DatabaseName": "customer_db",
    "Name": "customers",
    "ColumnNames": ["name"]
  }}' \
  --lf-tags '[
    {"TagKey": "PII_Classification", "TagValues": ["HIGH"]},
    {"TagKey": "PII_Type", "TagValues": ["NAME"]},
    {"TagKey": "Data_Sensitivity", "TagValues": ["HIGH"]}
  ]'
```

Claude grants tag-based access:

```bash
# Analysts get MEDIUM/LOW only (won't see names/emails)
aws lakeformation grant-permissions \
  --principal "arn:aws:iam::ACCOUNT:role/AnalystRole" \
  --resource '{"LFTagPolicy": {
    "ResourceType": "COLUMN",
    "Expression": [{
      "TagKey": "Data_Sensitivity",
      "TagValues": ["MEDIUM", "LOW"]
    }]
  }}' \
  --permissions SELECT
```

**Result:** Analysts can query the table but `name` and `email` columns return NULL.

---

## Natural Language Governance (MCP)

After onboarding, you can manage access via Claude Code:

### Example 1: Grant Access

**User prompt:**
```
Grant marketing-team access to customer names and cities, but NOT emails or SSNs
```

**Claude Code action:**
1. Identifies columns:
   - `name` → HIGH ✅
   - `city` → MEDIUM ✅
   - `email` → HIGH ❌
   - `ssn` → CRITICAL ❌

2. Calls MCP tool: `apply_column_security`
   - Principal: `arn:aws:iam::ACCOUNT:role/MarketingTeam`
   - Sensitivity: `['HIGH', 'MEDIUM']` (limited to name/city types only)

3. Lake Formation grants permissions

**Result:** Marketing team can see names and cities, but NOT emails or SSNs.

### Example 2: Compliance Report

**User prompt:**
```
Generate PII compliance report for customer_db
```

**Claude Code action:**
1. Calls MCP tool: `get_pii_report`
   - Database: `customer_db`
   - Format: `summary`

2. Returns JSON:
```json
{
  "database": "customer_db",
  "tables_with_pii": 3,
  "summary": {
    "critical": 2,  // SSN, credit cards
    "high": 12,     // Names, emails, DOB
    "medium": 8,    // Phone, address
    "low": 0
  },
  "compliance": ["GDPR", "CCPA"],
  "audit_trail": "CloudTrail enabled (7-year retention)"
}
```

### Example 3: Detect PII in New Table

**User prompt:**
```
Scan the new orders table for PII and apply appropriate tags
```

**Claude Code action:**
1. Calls MCP tool: `detect_pii_in_table`
   - Database: `customer_db`
   - Table: `orders`
   - Content detection: `true`
   - Apply tags: `true`

2. AI analyzes columns and sample data

3. Applies LF-Tags to detected PII columns

**Result:** Orders table now has column-level security.

---

## Key Benefits

### For Users
- **No manual PII tagging** — AI detects automatically
- **Regulatory compliance out-of-the-box** — GDPR, CCPA, HIPAA, SOX, PCI DSS
- **Natural language governance** — "Grant X access to Y" works via MCP
- **Audit-ready** — CloudTrail logs all access

### For Admins
- **Consistent governance** — Every workload follows same rules
- **Centralized control** — Lake Formation manages all permissions
- **Easy reporting** — Generate compliance reports on demand
- **Column-level security** — Fine-grained access without app changes

### For Compliance Teams
- **PII inventory** — Automated catalog of all sensitive columns
- **Access tracking** — CloudTrail logs who accessed what when
- **Data lineage** — Track PII from source to consumption
- **Retention policies** — Auto-expire data after N days

---

## Example: Healthcare Use Case (HIPAA)

See full demo:
```bash
python3 workloads/healthcare_patients/demo_governance_workflow.py
```

**Dataset:** 20 patients with PHI (names, SSN, DOB, medical records)

**Detected PII:**
- 2 CRITICAL columns (SSN, medical record number)
- 4 HIGH columns (name, email, DOB, visit date)
- 5 MEDIUM columns (phone, address, city, state, zip)

**Access Control:**
- **Admin:** ALL columns
- **Healthcare Provider:** HIGH + MEDIUM (can see names, NOT SSNs)
- **Analyst:** MEDIUM only (can see city/state, NOT names)
- **Dashboard:** NONE (aggregated data only)

**Compliance:** HIPAA controls applied (encryption, audit logs, 7-year retention)

---

## Comparison: Before vs After

| Aspect | Before Governance Framework | After Governance Framework |
|--------|---------------------------|--------------------------|
| **PII Detection** | Manual review, error-prone | AI-driven, automatic |
| **Access Control** | Table-level (all or nothing) | Column-level (fine-grained) |
| **Compliance** | Custom code per regulation | Built-in (GDPR, CCPA, HIPAA, etc.) |
| **Audit Trail** | Optional, inconsistent | Automatic (CloudTrail) |
| **Management** | AWS CLI, manual commands | Natural language (MCP) |
| **Onboarding Time** | Hours to configure security | Minutes (automatic) |
| **Consistency** | Varies per workload | Uniform across all workloads |

---

## Summary

The governance framework turns PII detection from a **manual, error-prone task** into a **built-in, automatic feature** of every data onboarding workflow.

**Key Integration Points:**

1. **Phase 1 Discovery** → Ask about regulations first
2. **Phase 3 Profiling** → PII detection runs automatically
3. **Phase 4 Build** → Masking rules generated
4. **Phase 5 Deploy** → LF-Tags applied, access granted
5. **Ongoing** → Natural language management via MCP

**No user action required** — it just works.

---

**Related Files:**
- `docs/governance-framework.md` — Complete framework documentation
- `shared/utils/pii_detection_and_tagging.py` — Detection engine
- `mcp-servers/pii-detection-server/` — MCP server for natural language governance
- `workloads/healthcare_patients/demo_governance_workflow.py` — Live demo
- `CLAUDE.md` — Security rules (Section: Security Rules)
- `SKILLS.md` — Discovery questions (Phase 1, Section 6a-6d)
