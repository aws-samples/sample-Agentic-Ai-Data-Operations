# PII Detection MCP Server - Usage Examples

**How to use the PII detection MCP server with natural language in Claude Code**

---

## Prerequisites

1. **MCP Server Configuration** (already done ✅)
   ```bash
   ~/.mcp.json contains pii-detection server config
   ```

2. **AWS Credentials** (already configured ✅)
   ```bash
   ~/.aws/credentials with Glue, Athena, Lake Formation permissions
   ```

3. **Claude Code Restart** (needed)
   ```
   Restart Claude Code to load the MCP server
   ```

---

## Natural Language Examples

### Example 1: Detect PII in a Table

**User Prompt:**
```
Scan the finsights_silver.funds_clean table for PII and show me what you find
```

**What happens behind the scenes:**
```json
{
  "tool": "detect_pii_in_table",
  "params": {
    "database": "finsights_silver",
    "table": "funds_clean",
    "content_detection": true,
    "apply_tags": false
  }
}
```

**Expected Response:**
```
I found PII in the funds_clean table:

Column: fund_manager_email
- PII Type: EMAIL
- Sensitivity: HIGH
- Detection: Name-based + Content (98% confidence)

Column: fund_manager_name
- PII Type: NAME
- Sensitivity: HIGH
- Detection: Name-based

Column: contact_phone
- PII Type: PHONE
- Sensitivity: MEDIUM
- Detection: Name-based + Content (100% confidence)

Summary: 3 PII columns detected
- HIGH: 2 columns
- MEDIUM: 1 column
```

---

### Example 2: Scan Entire Database

**User Prompt:**
```
Check all tables in the finsights_gold database for PII
```

**What happens:**
```json
{
  "tool": "scan_database_for_pii",
  "params": {
    "database": "finsights_gold",
    "content_detection": false,
    "apply_tags": false
  }
}
```

**Expected Response:**
```
PII scan results for finsights_gold database:

Table: customer_data
- PII columns: 5
- Sensitivity: CRITICAL (1), HIGH (3), MEDIUM (1)

Table: orders
- PII columns: 2
- Sensitivity: HIGH (2)

Table: analytics_summary
- PII columns: 0

Overall:
- Tables with PII: 2 / 3
- Total PII columns: 7
- CRITICAL: 1, HIGH: 5, MEDIUM: 1
```

---

### Example 3: Apply Lake Formation Tags

**User Prompt:**
```
Detect PII in finsights_silver.customer_master and automatically apply Lake Formation tags
```

**What happens:**
```json
{
  "tool": "detect_pii_in_table",
  "params": {
    "database": "finsights_silver",
    "table": "customer_master",
    "content_detection": true,
    "apply_tags": true
  }
}
```

**Expected Response:**
```
✓ PII detected in customer_master table
✓ Applied Lake Formation tags:

Column: email
- LF-Tags: PII_Classification=HIGH, PII_Type=EMAIL, Data_Sensitivity=HIGH

Column: ssn
- LF-Tags: PII_Classification=CRITICAL, PII_Type=SSN, Data_Sensitivity=CRITICAL

Column: phone
- LF-Tags: PII_Classification=MEDIUM, PII_Type=PHONE, Data_Sensitivity=MEDIUM

All columns tagged successfully. Use apply_column_security to configure access control.
```

---

### Example 4: Configure Access Control

**User Prompt:**
```
Grant the analyst role access to columns with LOW and MEDIUM PII sensitivity in the finsights_gold database
```

**What happens:**
```json
{
  "tool": "apply_column_security",
  "params": {
    "principal_arn": "arn:aws:iam::123456789012:role/AnalystRole",
    "sensitivity_levels": ["LOW", "MEDIUM"],
    "database": "finsights_gold"
  }
}
```

**Expected Response:**
```
✓ Applied column-level access control

Principal: AnalystRole
Allowed Sensitivity: LOW, MEDIUM
Database: finsights_gold

Granted SELECT on:
- finsights_gold.customer_data.phone (MEDIUM)
- finsights_gold.customer_data.city (MEDIUM)
- finsights_gold.customer_data.state (MEDIUM)
- finsights_gold.customer_data.zip_code (LOW)

Denied access to:
- finsights_gold.customer_data.ssn (CRITICAL)
- finsights_gold.customer_data.email (HIGH)
- finsights_gold.customer_data.name (HIGH)

Total: 4 columns granted, 3 columns denied
```

---

### Example 5: Generate Compliance Report

**User Prompt:**
```
Generate a PII compliance report for the finsights_silver database in summary format
```

**What happens:**
```json
{
  "tool": "get_pii_report",
  "params": {
    "database": "finsights_silver",
    "format": "summary"
  }
}
```

**Expected Response:**
```
PII Compliance Report - finsights_silver
========================================

Database: finsights_silver
Tables: 8
Tables with PII: 5 (62.5%)
Total PII columns: 23

Sensitivity Distribution:
- CRITICAL: 3 columns (13%)
  • customer_master.ssn
  • transactions.credit_card_number
  • accounts.bank_account

- HIGH: 12 columns (52%)
  • customer_master.email
  • customer_master.first_name
  • customer_master.last_name
  ... (9 more)

- MEDIUM: 6 columns (26%)
  • customer_master.phone
  • customer_master.address
  ... (4 more)

- LOW: 2 columns (9%)
  • customer_master.zip_code
  • logs.ip_address

Compliance Status:
✓ All CRITICAL PII tagged
✓ Access controls configured
⚠ Review 3 tables without PII detection
```

---

### Example 6: Query Specific PII Columns

**User Prompt:**
```
Show me all CRITICAL PII columns in the customer_master table
```

**What happens:**
```json
{
  "tool": "get_pii_columns",
  "params": {
    "database": "finsights_silver",
    "table": "customer_master",
    "sensitivity_level": "CRITICAL"
  }
}
```

**Expected Response:**
```
CRITICAL PII columns in customer_master:

1. ssn
   - PII Type: SSN
   - Sensitivity: CRITICAL
   - LF-Tags: Applied
   - Description: Social Security Number
   - Sample Pattern: XXX-XX-XXXX

2. credit_card_last4
   - PII Type: CREDIT_CARD
   - Sensitivity: CRITICAL
   - LF-Tags: Applied
   - Description: Last 4 digits of credit card
   - Sample Pattern: XXXX

Total: 2 CRITICAL PII columns found
```

---

### Example 7: Create LF-Tags (Setup)

**User Prompt:**
```
Set up Lake Formation tags for PII classification
```

**What happens:**
```json
{
  "tool": "create_lf_tags",
  "params": {
    "force_recreate": false
  }
}
```

**Expected Response:**
```
✓ Created Lake Formation Tags:

1. PII_Classification
   Values: CRITICAL, HIGH, MEDIUM, LOW, NONE
   Description: Primary PII classification level

2. PII_Type
   Values: SSN, CREDIT_CARD, EMAIL, PHONE, NAME, ADDRESS, DOB,
           BANK_ACCOUNT, PASSPORT, DRIVERS_LICENSE, IP_ADDRESS, ZIP_CODE
   Description: Specific PII data type

3. Data_Sensitivity
   Values: CRITICAL, HIGH, MEDIUM, LOW
   Description: Overall data sensitivity level

All tags created successfully. Ready to apply to columns.
```

---

## Advanced Workflows

### Workflow 1: Onboard New Data with PII Detection

```
1. "Detect PII in the new_customer_data table"
   → Identifies PII columns

2. "Apply Lake Formation tags to those columns"
   → Tags columns with PII_Classification, PII_Type

3. "Grant data-engineer role access to LOW and MEDIUM PII"
   → Configures tag-based access control

4. "Generate a compliance report for new_customer_data"
   → Documents PII findings for audit
```

---

### Workflow 2: Audit Existing Database

```
1. "Scan the entire production_db database for PII"
   → Database-wide PII inventory

2. "Show me all CRITICAL PII columns across all tables"
   → Security-critical data identification

3. "Generate a JSON compliance report for production_db"
   → Machine-readable audit output
```

---

### Workflow 3: Troubleshoot Access Issues

```
User: "Why can't the analyst role see the customer_email column?"

Claude: Let me check the PII tags on that column...
→ "Get PII columns in customer_data table"

Result: customer_email is tagged as HIGH sensitivity

Claude: The analyst role only has access to LOW and MEDIUM.
        Would you like me to update the access policy?
```

---

## Testing the MCP Server

### Quick Test Commands

Once Claude Code loads the MCP server, test with:

```
# Test 1: List all tools
"What PII detection tools do you have available?"

# Test 2: Simple detection
"Detect PII in sample_data/sales_transactions.csv"
(Note: MCP server works with Glue tables, not local CSV)

# Test 3: Full workflow
"Set up PII detection and tagging for the test_database"
```

---

## Troubleshooting

### Issue: MCP server not loading

**Check:**
```bash
# Verify configuration
cat ~/.mcp.json | grep pii-detection

# Test server manually
echo '{"method":"tools/list"}' | python3 mcp-servers/pii-detection-server/server.py
```

**Solution:**
- Restart Claude Code
- Verify server.py is executable: `chmod +x server.py`
- Check AWS credentials: `aws sts get-caller-identity`

---

### Issue: AWS permissions error

**Required IAM permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetDatabase",
        "athena:StartQueryExecution",
        "athena:GetQueryResults",
        "lakeformation:CreateLFTag",
        "lakeformation:AddLFTagsToResource",
        "lakeformation:GetLFTag",
        "lakeformation:ListLFTags",
        "lakeformation:GrantPermissions"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Documentation References

- **Full Test Report**: `PII_DETECTION_TEST_REPORT.md`
- **Server README**: `mcp-servers/pii-detection-server/README.md`
- **Python Script**: `shared/utils/pii_detection_and_tagging.py`
- **Test Script**: `test_pii_detection.py`

---

**Status**: Ready for natural language interaction once Claude Code loads the MCP server
**Last Updated**: March 17, 2026
