# Healthcare Patients Data Pipeline

**Status**: ✅ Generated - Ready for Deployment
**Compliance**: HIPAA (Health Insurance Portability and Accountability Act)
**Owner**: Healthcare Operations Team
**Created**: 2026-03-24

## Overview

HIPAA-compliant data pipeline for patient visit records. Implements PHI encryption, 7-year audit retention, minimum necessary access control, and comprehensive HIPAA compliance checks.

## Data Flow

```
CSV Source (20 patients, 16 columns)
  ↓
Bronze Zone (Landing) - Raw ingestion, encrypted
  ↓ Extract + Validate
Silver Zone (Staging) - Cleaned, PII masked, validated
  ↓ Quality Gate (95% threshold, HIPAA checks)
Gold Zone (Publish) - Star schema, aggregated, de-identified
  ↓
QuickSight Dashboards (aggregated metrics only)
```

## PHI Classification

### CRITICAL (2 columns)
- `ssn`: Social Security Number → SHA-256 hash in Staging
- `medical_record_number`: Hospital MRN → Tokenized in Staging

### HIGH (4 columns)
- `patient_name`: Full name → SHA-256 hash in Staging
- `email`: Email address → mask_email (j***@email.com)
- `dob`: Date of birth → Used for age calculations only
- `visit_date`: Visit date → Aggregated in Publish

### MEDIUM (5 columns)
- `phone`: Phone number → mask_partial (555-***-4567)
- `address, city, state, zip`: Geography → Kept for analysis (TBAC enforced)

### LOW (5 columns)
- `blood_type, diagnosis, treatment_cost, insurance_provider, patient_id`: Non-PHI

## HIPAA Compliance Controls

### 1. Encryption
- **At Rest**: AES-256 via KMS key `alias/hipaa-phi-key`
- **In Transit**: TLS 1.3
- **Key Rotation**: Annual (automatic)
- **Zones**: All zones (Bronze, Silver, Gold) use same HIPAA key

### 2. Access Control (TBAC - Minimum Necessary)
| Role | Sensitivity Levels | Justification |
|------|-------------------|---------------|
| Admin | ALL (CRITICAL, HIGH, MEDIUM, LOW) | System administration, compliance |
| Healthcare Provider | HIGH, MEDIUM, LOW | Patient care (no SSN access) |
| Billing | HIGH, MEDIUM, LOW | Claims processing |
| Analyst | MEDIUM, LOW | Population health (no individual PHI) |
| Dashboard User | LOW | Aggregated metrics only |

### 3. Data Retention
- **Landing**: 90 days (temporary raw storage)
- **Staging**: 2555 days (7 years - HIPAA minimum)
- **Publish**: 2555 days (7 years - HIPAA minimum)
- **Audit Logs**: 2555 days (immutable S3 Object Lock)

### 4. Audit Trail
- **Service**: CloudTrail
- **Tracked Events**: GetDataAccess, AddLFTagsToResource, GrantPermissions, RevokePermissions
- **Retention**: 2555 days (7 years)
- **Immutability**: S3 Object Lock enabled (GOVERNANCE mode)

### 5. PII Masking
| Column | Method | Example |
|--------|--------|---------|
| ssn | SHA-256 hash | `123-45-6789` → `a1b2c3...` |
| patient_name | SHA-256 hash | `John Smith` → `d4e5f6...` |
| email | mask_email | `john@email.com` → `j***@email.com` |
| phone | mask_partial | `555-123-4567` → `555-***-4567` |
| medical_record_number | tokenize | `MRN-2025-001` → `MRN-TOKEN-001` |

### 6. Quality Rules (HIPAA-Specific)
- ✅ All PHI columns encrypted at rest (100% threshold)
- ✅ All PHI columns tagged with LF-Tags (100% threshold)
- ✅ CloudTrail enabled for audit logging (100% threshold)
- ✅ No PHI in application logs or error messages (100% threshold)
- ✅ Provider role cannot access CRITICAL PHI (SSN, MRN) (100% threshold)

## Business Associate Agreement (BAA)

✅ **AWS BAA Active**: Covers S3, Glue, Athena, Lake Formation, KMS, CloudTrail

**Documented**: BAA signed on [DATE] for AWS account 133661573128

**Scope**: All AWS services used in this pipeline are covered under the BAA

## Breach Notification

**Deadline**: 60 days from discovery of PHI breach

**Procedure**:
1. Immediately escalate to healthcare-ops-team@hospital.com and compliance-team@hospital.com
2. Investigate scope of breach (which PHI columns, how many records, who accessed)
3. Document breach details in incident response system
4. Notify affected individuals within 60 days (HIPAA requirement)
5. Submit breach report to HHS if >500 individuals affected

## Semantic Layer

### Measures
- `treatment_cost`: SUM - Total treatment charges (USD)
- `patient_count`: COUNT DISTINCT - Unique patient count
- `visit_count`: COUNT - Total visits
- `avg_treatment_cost`: AVG - Average cost per visit (USD)

### Dimensions
- `blood_type`: O+, O-, A+, A-, B+, B-, AB+, AB-
- `diagnosis`: Hypertension, Diabetes, Asthma, etc.
- `insurance_provider`: Blue Cross, Aetna, UnitedHealth, Cigna, Humana, Kaiser
- `state, city`: Geography (PHI - MEDIUM sensitivity)

### Seed Questions (Top 10)
1. What was total revenue last month?
2. How many patients visited in Q1?
3. What's the average treatment cost by diagnosis?
4. Which insurance provider has the most patients?
5. Show me patient visits by state
6. What's our month-over-month revenue growth?
7. Which blood type has highest treatment costs?
8. How many patients are over 65?
9. What's the revenue breakdown by month?
10. Which diagnoses generate the most revenue?

## Pipeline Schedule

- **Frequency**: Daily at 2:00 AM UTC
- **SLA**: 2 hours
- **Retries**: 3 with exponential backoff
- **Notifications**: Email (healthcare-ops-team@hospital.com) + Slack (#healthcare-data-alerts)

## Directory Structure

```
workloads/healthcare_patients/
├── config/                      # Configuration files
│   ├── source.yaml             # Source schema and PHI classification
│   ├── semantic.yaml           # Semantic layer (measures, dimensions, seed questions)
│   ├── transformations.yaml    # PII masking and cleaning rules
│   ├── quality_rules.yaml      # HIPAA compliance checks
│   └── schedule.yaml           # DAG schedule and orchestration
├── scripts/                     # ETL scripts
│   ├── extract/
│   │   └── landing_to_s3.py   # Bronze ingestion
│   ├── transform/
│   │   ├── staging_clean.py   # Silver cleaning with PII masking
│   │   └── publish_star_schema.py  # Gold star schema
│   └── quality/
│       └── run_checks.py       # HIPAA compliance verification
├── dags/
│   └── healthcare_patients_pipeline.py  # Airflow DAG with audit logging
├── sql/
│   ├── bronze/                 # Raw SQL
│   ├── silver/                 # Cleaned SQL
│   └── gold/                   # Star schema SQL
├── tests/
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration + HIPAA tests
├── logs/                        # Pipeline execution traces
│   ├── README.md
│   └── .gitignore
├── sample_data/
│   └── patients.csv            # Test data (20 patient records)
├── deploy_to_aws.py            # Deployment script
├── ONBOARDING_SPEC.md          # Complete onboarding specification
└── README.md                   # This file
```

## Deployment

### Prerequisites
- ✅ KMS key `alias/hipaa-phi-key` exists (created in Phase 0)
- ✅ LF-Tags exist: PII_Classification, PII_Type, Data_Sensitivity
- ⏳ IAM roles: Admin, Provider, Billing, Analyst, Dashboard User (created during deployment)
- ✅ MWAA environment ready
- ✅ CloudTrail enabled

### Deploy to AWS
```bash
python3 deploy_to_aws.py
```

**What it does**:
1. Creates Glue databases (healthcare_patients_bronze, _silver, _gold)
2. Uploads scripts to S3
3. Registers Iceberg tables in Glue Catalog
4. Applies LF-Tags to all PHI columns
5. Grants TBAC permissions (5 roles)
6. Deploys DAG to MWAA
7. Runs 7 HIPAA verification smoke tests

### Post-Deployment Verification

```bash
# 1. Verify KMS encryption on S3 buckets
aws s3api get-bucket-encryption --bucket prod-data-lake

# 2. Verify LF-Tags applied to PHI columns
aws lakeformation get-resource-lf-tags \
  --resource '{"TableWithColumns": {"DatabaseName": "healthcare_patients_silver", "Name": "patient_visits", "ColumnNames": ["ssn", "patient_name"]}}'

# 3. Verify TBAC grants (Provider should NOT see CRITICAL)
aws lakeformation list-permissions \
  --principal '{"DataLakePrincipalIdentifier": "arn:aws:iam::133661573128:role/ProviderRole"}'

# 4. Test minimum necessary (Provider queries SSN — should return NULL or AccessDenied)
aws athena start-query-execution \
  --query-string "SELECT ssn FROM healthcare_patients_silver.patient_visits LIMIT 5" \
  --result-configuration "OutputLocation=s3://prod-data-lake/query-results/"

# 5. Verify CloudTrail logging active
aws cloudtrail get-trail-status --name IsengardTrail-DO-NOT-DELETE

# 6. Verify audit log retention (S3 Object Lock)
aws s3api get-object-lock-configuration --bucket ${AUDIT_BUCKET}

# 7. Verify KMS key rotation enabled
aws kms get-key-rotation-status --key-id alias/hipaa-phi-key
```

## Testing

### Run Tests Locally
```bash
# All tests
pytest workloads/healthcare_patients/tests/ -v

# Unit tests only
pytest workloads/healthcare_patients/tests/unit/ -v

# Integration tests only
pytest workloads/healthcare_patients/tests/integration/ -v

# HIPAA compliance tests
pytest workloads/healthcare_patients/tests/integration/test_hipaa_compliance.py -v
```

### Test Coverage
- Unit tests: Transformations, quality rules, PII masking
- Integration tests: End-to-end pipeline, HIPAA compliance
- Expected: 50+ tests with 80%+ coverage

## Monitoring

### CloudWatch Dashboards
- Pipeline execution duration
- Quality score trends
- PHI access patterns (audit trail)
- Data volume trends

### Alerts
- **Critical**: Pipeline failure, HIPAA compliance check failure
- **High**: Quality score < 0.95, PII detected in logs
- **Medium**: Retry exhausted, SLA breach

### Audit Reports
- Monthly PHI access report
- Quarterly compliance report
- Annual HIPAA audit

## References

- HIPAA regulation controls: `prompts/data-onboarding-agent/regulation/hipaa.md`
- PII detection utility: `shared/utils/pii_detection_and_tagging.py`
- Cedar policies: `shared/policies/guardrails/`
- Governance framework: `docs/governance-framework.md` (lines 140-165)

## Contact

- **Owner**: Healthcare Operations Team
- **Email**: healthcare-ops-team@hospital.com
- **Slack**: #healthcare-data-alerts
- **Compliance**: compliance-team@hospital.com

---

**Generated**: 2026-03-24
**Status**: ✅ Ready for Deployment
**Compliance**: HIPAA
**Version**: 1.0.0
