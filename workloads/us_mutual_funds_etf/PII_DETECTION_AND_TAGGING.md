# PII Detection and Lake Formation Tagging

**Feature:** Automated PII detection with Lake Formation Tag-Based Access Control (TBAC)
**Status:** ✅ IMPLEMENTED
**Created:** March 17, 2026

---

## Overview

Automatically identifies Personally Identifiable Information (PII) in data and applies AWS Lake Formation Tags (LF-Tags) for fine-grained access control and governance.

### Key Benefits

- **Automated Discovery:** Detects PII without manual column inspection
- **Compliance:** Helps meet GDPR, CCPA, HIPAA requirements
- **Access Control:** Enables tag-based column-level security
- **Audit Trail:** Complete logging of PII detection and tagging
- **Scalable:** Works across all tables in a database

---

## Features

### 1. PII Detection Methods

**Name-Based Detection:**
- Analyzes column names for PII indicators
- Pattern matching against known PII field names
- 100% confidence when name matches

**Content-Based Detection:**
- Samples actual column data (100 rows default)
- Applies regex patterns to detect PII formats
- Calculates confidence score based on match percentage

### 2. Supported PII Types

| PII Type | Pattern | Sensitivity | Example |
|----------|---------|-------------|---------|
| EMAIL | Email address format | HIGH | user@example.com |
| PHONE | US phone numbers | MEDIUM | (555) 123-4567 |
| SSN | Social Security Number | CRITICAL | 123-45-6789 |
| CREDIT_CARD | Credit card numbers | CRITICAL | 1234-5678-9012-3456 |
| DATE_OF_BIRTH | Date formats | HIGH | 01/15/1990 |
| ZIP_CODE | US ZIP codes | LOW | 12345 or 12345-6789 |
| IP_ADDRESS | IPv4 addresses | LOW | 192.168.1.1 |
| NAME | First/last name columns | HIGH | (name-based only) |
| ADDRESS | Street, city, state | HIGH | (name-based only) |
| BANK_ACCOUNT | Account numbers | CRITICAL | (name-based only) |
| PASSPORT | Passport numbers | CRITICAL | (name-based only) |
| DRIVERS_LICENSE | License numbers | CRITICAL | (name-based only) |

### 3. Sensitivity Levels

| Level | Description | Use Case |
|-------|-------------|----------|
| **CRITICAL** | Most sensitive PII | SSN, credit cards, bank accounts |
| **HIGH** | Identifiable information | Email, names, DOB |
| **MEDIUM** | Contact information | Phone numbers |
| **LOW** | Less sensitive location data | ZIP codes, IP addresses |

### 4. Lake Formation Tags Applied

**Three LF-Tags are created and applied:**

1. **PII_Classification**
   - Values: CRITICAL, HIGH, MEDIUM, LOW, NONE
   - Used for access policies

2. **PII_Type**
   - Values: EMAIL, PHONE, SSN, CREDIT_CARD, NAME, ADDRESS, etc.
   - Identifies specific PII type

3. **Data_Sensitivity**
   - Values: CRITICAL, HIGH, MEDIUM, LOW
   - Matches PII_Classification for consistency

---

## Usage

### Basic Usage

**Scan a single table:**
```bash
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_silver \
  --table funds_clean
```

**Scan all tables in a database:**
```bash
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_gold \
  --all-tables
```

### Advanced Options

**Skip content-based detection (faster):**
```bash
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_silver \
  --table customer_data \
  --no-content-detection
```

**Detect only, don't apply tags:**
```bash
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_gold \
  --table users \
  --no-tagging
```

**Save report to specific file:**
```bash
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_silver \
  --all-tables \
  --output pii_report_2026-03-17.json
```

---

## Integration with Data Pipeline

### Option 1: Manual Scan After ETL

Run PII detection after data is loaded:

```bash
# After Bronze job completes
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_bronze \
  --all-tables

# After Silver job completes
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_silver \
  --all-tables

# After Gold job completes
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_gold \
  --all-tables
```

### Option 2: Add to Airflow DAG

Add as a task in the DAG:

```python
from airflow.operators.python import PythonOperator
import subprocess

def run_pii_detection(**context):
    """Run PII detection and tagging"""
    cmd = [
        'python3',
        'scripts/governance/pii_detection_and_tagging.py',
        '--database', 'finsights_silver',
        '--all-tables'
    ]
    subprocess.run(cmd, check=True)

# Add to DAG
pii_detection_task = PythonOperator(
    task_id='pii_detection_and_tagging',
    python_callable=run_pii_detection,
    dag=dag
)

# Set dependencies
silver_stage >> pii_detection_task >> gold_stage
```

### Option 3: AWS Glue Job

Create a dedicated Glue job:

```bash
# Register job
aws glue create-job \
  --name pii_detection_and_tagging \
  --role GlueServiceRole \
  --command Name=pythonshell,ScriptLocation=s3://your-datalake-bucket/scripts/governance/pii_detection_and_tagging.py \
  --default-arguments '{"--database":"finsights_silver","--all-tables":"true"}' \
  --max-capacity 0.0625

# Run job
aws glue start-job-run --job-name pii_detection_and_tagging
```

---

## Output

### Console Output

```
================================================================================
PII DETECTION AND LAKE FORMATION TAGGING
================================================================================
Database: finsights_silver
Content detection: True
Apply LF-Tags: True

================================================================================
Ensuring Lake Formation Tags exist
================================================================================
✓ LF-Tag already exists: PII_Classification
✓ LF-Tag already exists: PII_Type
✓ LF-Tag already exists: Data_Sensitivity

================================================================================
Scanning table: finsights_silver.customer_data
================================================================================
Found 8 columns

Analyzing column: customer_id (bigint)
  ✓ No PII detected

Analyzing column: email (string)
  ✓ Name-based: EMAIL (HIGH)
Sampling column email for content-based PII detection...
  Detected EMAIL with 100.0% confidence
  ⚠️  PII DETECTED: EMAIL (Sensitivity: HIGH)

Analyzing column: phone (string)
  ✓ Name-based: PHONE (MEDIUM)
  ⚠️  PII DETECTED: PHONE (Sensitivity: MEDIUM)

...

================================================================================
Applying LF-Tags to finsights_silver.customer_data
================================================================================

Tagging column: email
  ✓ Applied tags: PII_Classification=HIGH, PII_Type=EMAIL

Tagging column: phone
  ✓ Applied tags: PII_Classification=MEDIUM, PII_Type=PHONE

✓ PII report saved to: pii_report_finsights_silver_customer_data_20260317_060000.json

================================================================================
SCAN COMPLETE
================================================================================
Tables scanned: 1
Tables with PII: 1
Total PII columns found: 2

PII Summary by Sensitivity:
  HIGH: 1 columns
  MEDIUM: 1 columns
```

### JSON Report

```json
{
  "scan_timestamp": "2026-03-17T06:00:00",
  "database": "finsights_silver",
  "table": "customer_data",
  "total_columns_scanned": 2,
  "pii_columns": {
    "email": {
      "pii_types": ["EMAIL"],
      "sensitivity": "HIGH",
      "confidence_scores": {
        "EMAIL": 100.0
      },
      "data_type": "string",
      "detection_methods": {
        "name_based": true,
        "content_based": true
      }
    },
    "phone": {
      "pii_types": ["PHONE"],
      "sensitivity": "MEDIUM",
      "confidence_scores": {
        "PHONE": 100.0
      },
      "data_type": "string",
      "detection_methods": {
        "name_based": true,
        "content_based": false
      }
    }
  },
  "summary": {
    "critical": 0,
    "high": 1,
    "medium": 1,
    "low": 0
  }
}
```

---

## Lake Formation Tag-Based Access Control

### Use LF-Tags for Access Policies

Once columns are tagged, use LF-Tags in permission grants:

**Example 1: Grant access to non-PII columns only**

```bash
# Grant access to all columns EXCEPT PII
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT_ID:role/AnalystRole" \
  --resource '{"LFTagPolicy":{"ResourceType":"TABLE","Expression":[{"TagKey":"PII_Classification","TagValues":["NONE"]}]}}' \
  --permissions SELECT
```

**Example 2: Grant access to low/medium sensitivity PII**

```bash
# Grant access to columns with PII_Classification = LOW or MEDIUM
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT_ID:role/DataScienceRole" \
  --resource '{"LFTagPolicy":{"ResourceType":"COLUMN","Expression":[{"TagKey":"PII_Classification","TagValues":["LOW","MEDIUM"]}]}}' \
  --permissions SELECT
```

**Example 3: Grant access to CRITICAL PII (restricted)**

```bash
# Only specific roles can access CRITICAL PII
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT_ID:role/ComplianceRole" \
  --resource '{"LFTagPolicy":{"ResourceType":"COLUMN","Expression":[{"TagKey":"PII_Classification","TagValues":["CRITICAL"]}]}}' \
  --permissions SELECT
```

**Example 4: Grant access to specific PII types**

```bash
# Grant access only to EMAIL columns
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT_ID:role/MarketingRole" \
  --resource '{"LFTagPolicy":{"ResourceType":"COLUMN","Expression":[{"TagKey":"PII_Type","TagValues":["EMAIL"]}]}}' \
  --permissions SELECT
```

---

## Verification

### Check LF-Tags on Columns

```bash
# List tags on a specific column
aws lakeformation get-resource-lf_tags \
  --resource '{"TableWithColumns":{"DatabaseName":"finsights_silver","Name":"customer_data","ColumnNames":["email"]}}' \
  --region us-east-1
```

**Expected Output:**
```json
{
  "LFTagsOnColumns": [
    {
      "Name": "email",
      "LFTags": [
        {"TagKey": "PII_Classification", "TagValues": ["HIGH"]},
        {"TagKey": "PII_Type", "TagValues": ["EMAIL"]},
        {"TagKey": "Data_Sensitivity", "TagValues": ["HIGH"]}
      ]
    }
  ]
}
```

### Query Tagged Columns

```bash
# Find all columns with CRITICAL PII
aws lakeformation search-tables-by-lf-tags \
  --expression '[{"TagKey":"PII_Classification","TagValues":["CRITICAL"]}]' \
  --region us-east-1
```

---

## Troubleshooting

### Issue: "AccessDeniedException" when tagging

**Cause:** Insufficient Lake Formation permissions

**Solution:**
```bash
# Grant LF-Tag management permissions
aws lakeformation grant-permissions \
  --principal "DataLakePrincipalIdentifier=arn:aws:iam::ACCOUNT_ID:user/YOUR-USER" \
  --permissions CREATE_LF_TAG ASSOCIATE \
  --resource '{"LFTagPolicy":{"ResourceType":"DATABASE"}}'
```

### Issue: Content detection not finding PII

**Cause:** Sample size too small or data doesn't match patterns

**Solutions:**
1. Increase `SAMPLE_SIZE` in script (default: 100)
2. Add custom regex patterns to `PII_PATTERNS`
3. Add column name patterns to `COLUMN_NAME_PATTERNS`

### Issue: False positives in PII detection

**Cause:** Regex patterns matching non-PII data

**Solutions:**
1. Refine regex patterns in `PII_PATTERNS`
2. Increase confidence threshold (currently 10%)
3. Use `--no-content-detection` and rely on name-based detection only

### Issue: Query timeout during content detection

**Cause:** Large tables or slow Athena queries

**Solution:**
1. Reduce `SAMPLE_SIZE`
2. Increase `max_wait` timeout (default: 30 seconds)
3. Use `--no-content-detection` for faster scans

---

## Best Practices

### 1. Scan at Multiple Stages

Run PII detection at each zone:
- **Bronze:** Identify PII in raw data
- **Silver:** Verify PII carried through cleaning
- **Gold:** Confirm PII in business-ready data

### 2. Review Before Tagging

Use `--no-tagging` first to review detection results:

```bash
# Detect only, don't tag
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_silver \
  --table customer_data \
  --no-tagging

# Review pii_report_*.json
cat pii_report_*.json | jq '.pii_columns'

# If results look good, tag
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_silver \
  --table customer_data
```

### 3. Automate in CI/CD

Add PII detection to your deployment pipeline:

```yaml
# .github/workflows/deploy-pipeline.yml
- name: Run PII Detection
  run: |
    python3 scripts/governance/pii_detection_and_tagging.py \
      --database finsights_silver \
      --all-tables

    python3 scripts/governance/pii_detection_and_tagging.py \
      --database finsights_gold \
      --all-tables
```

### 4. Document PII Decisions

Save PII reports to S3 for audit trail:

```bash
# Save report to S3
python3 scripts/governance/pii_detection_and_tagging.py \
  --database finsights_gold \
  --all-tables \
  --output /tmp/pii_report.json

aws s3 cp /tmp/pii_report.json \
  s3://your-datalake-bucket/governance/pii-reports/$(date +%Y%m%d)/
```

### 5. Regular Rescans

Schedule periodic rescans to detect PII in new columns:

```bash
# Add to cron or Airflow DAG
# Run monthly after data refresh
0 3 1 * * python3 scripts/governance/pii_detection_and_tagging.py --database finsights_silver --all-tables
```

---

## Extending the Script

### Add Custom PII Patterns

Edit `PII_PATTERNS` dictionary:

```python
PII_PATTERNS = {
    'EMPLOYEE_ID': {
        'regex': r'\bEMP\d{6}\b',
        'description': 'Employee ID',
        'sensitivity': 'MEDIUM'
    },
    'CUSTOMER_NUMBER': {
        'regex': r'\bCUST\d{8}\b',
        'description': 'Customer number',
        'sensitivity': 'HIGH'
    },
    # ... existing patterns
}
```

### Add Custom Column Name Patterns

Edit `COLUMN_NAME_PATTERNS` dictionary:

```python
COLUMN_NAME_PATTERNS = {
    'EMPLOYEE_ID': ['emp_id', 'employee_id', 'employee_number'],
    'MEDICAL_ID': ['patient_id', 'medical_record', 'mrn'],
    # ... existing patterns
}
```

### Customize Sensitivity Levels

Modify sensitivity in `PII_PATTERNS`:

```python
'EMAIL': {
    'regex': r'...',
    'description': 'Email address',
    'sensitivity': 'MEDIUM'  # Changed from HIGH to MEDIUM
}
```

---

## Compliance Use Cases

### GDPR Compliance

**Article 32: Security of Processing**

Use PII tagging to:
1. Identify all personal data in your data lake
2. Apply encryption to columns tagged as PII
3. Restrict access based on data sensitivity
4. Maintain audit log of PII access

**Article 17: Right to Erasure**

Query for all PII columns:
```bash
# Find all tables with PII
aws lakeformation search-tables-by-lf-tags \
  --expression '[{"TagKey":"PII_Classification","TagValues":["CRITICAL","HIGH","MEDIUM"]}]'
```

### CCPA Compliance

**Right to Know / Right to Delete**

Use PII tags to:
1. Locate all consumer data
2. Generate data inventory reports
3. Implement deletion workflows

### HIPAA Compliance

**Protected Health Information (PHI)**

Tag PHI columns:
- Medical record numbers
- Health plan beneficiary numbers
- Device identifiers
- Biometric identifiers

Use LF-Tags to restrict access to authorized roles only.

---

## Cost Considerations

### Athena Query Costs

**Content-based detection:**
- Scans 100 rows per column
- Typical scan: 1-5 MB per table
- Cost: ~$0.000005 per table

**Example:**
- 100 tables × 10 columns × 100 rows = ~50 MB scanned
- Cost: ~$0.00025 (negligible)

### Lake Formation Costs

**LF-Tags:** Free
**No additional cost** for applying or using LF-Tags

### Script Execution

**Lambda:** $0.0000166667 per GB-second
**Glue Python Shell:** $0.44 per DPU-hour (0.0625 DPU)

**Cost per run:** < $0.03

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| **PII_DETECTION_AND_TAGGING.md** | This document |
| **LAKE_FORMATION_S3_REGISTRATION_FIX.md** | S3 registration for LF |
| **DEMO_ROLE_ACCESS.md** | User access configuration |
| **PROJECT_COMPLETE.md** | Full project summary |

---

**Feature Status:** ✅ Implemented and ready for use
**Script Location:** `scripts/governance/pii_detection_and_tagging.py`
**Created:** March 17, 2026 @ 6:15 AM EST
