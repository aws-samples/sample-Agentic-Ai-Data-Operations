# Healthcare Patients Onboarding Specification - HIPAA Compliant

**Status**: ✅ Specification Complete - Ready for Phase 0-5 Execution
**Created**: 2026-03-24
**Regulation**: HIPAA (Health Insurance Portability and Accountability Act)

## Overview

This document specifies the complete onboarding configuration for the healthcare_patients workload with HIPAA compliance controls. All default values have been provided based on HIPAA regulatory requirements and platform best practices.

## Source Data

**Location**: `workloads/healthcare_patients/sample_data/patients.csv`
**Records**: 20 patient visit records (test dataset)
**Columns**: 16 (11 PHI columns, 5 non-PHI columns)

### PHI Classification

| Column | PHI Type | Sensitivity | HIPAA Category |
|--------|----------|-------------|----------------|
| ssn | SSN | CRITICAL | Social Security Number |
| medical_record_number | NATIONAL_ID | CRITICAL | Medical Record Number |
| patient_name | NAME | HIGH | Name |
| email | EMAIL | HIGH | Contact info |
| dob | DOB | HIGH | Dates related to individual |
| visit_date | DOB | HIGH | Dates related to individual |
| phone | PHONE | MEDIUM | Telephone number |
| address | ADDRESS | MEDIUM | Geographic data |
| city | ADDRESS | MEDIUM | Geographic data |
| state | ADDRESS | MEDIUM | Geographic data |
| zip | ADDRESS | MEDIUM | Geographic data |
| blood_type | — | LOW | Non-PHI |
| diagnosis | — | LOW | Non-PHI (but sensitive) |
| treatment_cost | — | LOW | Non-PHI |
| insurance_provider | — | LOW | Non-PHI |
| patient_id | — | LOW | Non-PHI identifier |

## HIPAA Compliance Configuration

### 1. Encryption (Default Values Applied)

```yaml
encryption:
  landing:
    kms_key_alias: alias/hipaa-phi-key
    algorithm: AES-256
    transport: TLS 1.3
  staging:
    kms_key_alias: alias/hipaa-phi-key
    algorithm: AES-256
    transport: TLS 1.3
  publish:
    kms_key_alias: alias/hipaa-phi-key
    algorithm: AES-256
    transport: TLS 1.3
  glue_catalog:
    kms_key_alias: alias/catalog-metadata-key
  key_rotation:
    enabled: true
    frequency: annual
```

### 2. Access Control (Default Roles Applied)

```yaml
access_control:
  minimum_necessary: true
  roles:
    - name: Admin
      sensitivity_levels: [CRITICAL, HIGH, MEDIUM, LOW]
      justification: System administration, compliance auditing
    - name: Healthcare Provider
      sensitivity_levels: [HIGH, MEDIUM, LOW]
      justification: Patient care (no SSN access per minimum necessary)
    - name: Billing
      sensitivity_levels: [HIGH, MEDIUM, LOW]
      justification: Claims processing (no SSN needed)
    - name: Analyst
      sensitivity_levels: [MEDIUM, LOW]
      justification: Population health analytics (no individual PHI)
    - name: Dashboard User
      sensitivity_levels: [LOW]
      justification: Aggregated metrics only
```

### 3. Data Retention (Default Values Applied)

```yaml
data_retention:
  landing:
    days: 90
    reason: Raw data temporary storage
  staging:
    days: 2555  # 7 years - HIPAA minimum
    reason: HIPAA audit trail requirement
  publish:
    days: 2555  # 7 years - HIPAA minimum
    reason: HIPAA audit trail requirement
  audit_logs:
    days: 2555  # 7 years - HIPAA minimum
    immutable: true
    storage_class: S3 Glacier Deep Archive
    object_lock: true
```

### 4. Audit Logging (Default Values Applied)

```yaml
audit_logging:
  enabled: true
  service: CloudTrail
  retention_days: 2555  # 7 years
  immutable: true
  tracked_events:
    - GetDataAccess
    - AddLFTagsToResource
    - GrantPermissions
    - RevokePermissions
    - BatchGrantPermissions
    - BatchRevokePermissions
  attributes:
    - user_identity
    - source_ip_address
    - timestamp
    - operation_name
    - resource_arn
    - success_failure
  storage:
    bucket: ${account_id}-audit-logs-us-east-1
    encryption: alias/audit-log-key
    object_lock:
      enabled: true
      mode: GOVERNANCE
      days: 2555
```

### 5. PII Masking (Default Methods Applied)

```yaml
pii_masking:
  staging:
    ssn:
      method: hash
      algorithm: SHA-256
      example: "123-45-6789" -> "a1b2c3d4e5f6..."
    patient_name:
      method: hash
      algorithm: SHA-256
      example: "John Smith" -> "d4e5f6a7b8c9..."
    email:
      method: mask_email
      example: "john.smith@email.com" -> "j***@email.com"
    phone:
      method: mask_partial
      example: "555-123-4567" -> "555-***-4567"
    medical_record_number:
      method: tokenize
      example: "MRN-2025-001" -> "MRN-TOKEN-001"
    address:
      method: keep  # Needed for geography analysis (MEDIUM sensitivity)
    city:
      method: keep  # Needed for geography analysis
    state:
      method: keep  # Needed for geography analysis
    zip:
      method: keep  # Needed for geography analysis
  publish:
    # De-identification for aggregated tables
    all_phi:
      method: aggregate_only
      description: Only aggregated metrics, no individual PHI
```

### 6. Quality Rules (Default Thresholds Applied)

```yaml
quality_rules:
  completeness:
    - columns: [patient_id, medical_record_number, ssn, visit_date]
      threshold: 1.0  # 100%
      severity: critical

  uniqueness:
    - columns: [patient_id, visit_date]
      threshold: 1.0  # 100%
      severity: critical

  validity:
    - column: blood_type
      values: [O+, O-, A+, A-, B+, B-, AB+, AB-]
      threshold: 0.95  # 95%
      severity: high
    - column: state
      validation: valid_us_state
      threshold: 1.0  # 100%
      severity: high
    - column: treatment_cost
      range: [0, 1000000]
      threshold: 1.0  # 100%
      severity: critical
    - column: visit_date
      range: [1900-01-01, CURRENT_DATE]
      threshold: 1.0  # 100%
      severity: critical
    - column: dob
      range: [1900-01-01, CURRENT_DATE]
      threshold: 1.0  # 100%
      severity: critical

  hipaa_compliance:
    - rule: phi_columns_encrypted
      check: encryption_enabled
      columns: [patient_name, dob, ssn, email, phone, address, city, state, zip, medical_record_number]
      threshold: 1.0  # 100%
      severity: critical
      description: HIPAA requires all PHI encrypted at rest

    - rule: phi_columns_tagged
      check: lf_tags_applied
      columns: [patient_name, dob, ssn, email, phone, address, city, state, zip, medical_record_number]
      threshold: 1.0  # 100%
      severity: critical
      description: All PHI must have LF-Tags for access control

    - rule: audit_logging_active
      check: cloudtrail_enabled
      threshold: 1.0  # 100%
      severity: critical
      description: HIPAA requires audit trail for all PHI access

    - rule: phi_not_in_logs
      check: no_pii_in_logs
      threshold: 1.0  # 100%
      severity: critical
      description: PHI must never appear in logs or error messages

    - rule: minimum_necessary_access
      check: provider_role_cannot_access_ssn
      threshold: 1.0  # 100%
      severity: critical
      description: Provider role must not access CRITICAL PHI (SSN)
```

### 7. Orchestration (Default Schedule Applied)

```yaml
orchestration:
  schedule:
    cron: "0 2 * * *"  # Daily at 2:00 AM UTC
    description: Daily patient visit data ingestion

  sla:
    duration_minutes: 120  # 2 hours
    action: alert

  retries:
    max_attempts: 3
    backoff_strategy: exponential
    base_delay_seconds: 60

  notifications:
    on_failure:
      email: healthcare-ops-team@hospital.com
      slack: #healthcare-data-alerts
    on_success:
      email: healthcare-ops-team@hospital.com

  dependencies:
    upstream: []  # Independent pipeline
    downstream: []
```

### 8. Semantic Layer (Default Measures & Dimensions)

```yaml
semantic_layer:
  fact_grain: "One row = one patient visit"

  measures:
    - name: treatment_cost
      aggregation: SUM
      description: "Total treatment cost across visits"
      unit: USD
      format: "$#,##0.00"

    - name: patient_count
      aggregation: COUNT_DISTINCT
      source: patient_id
      description: "Unique patient count"
      unit: count

    - name: visit_count
      aggregation: COUNT
      description: "Total number of visits"
      unit: count

    - name: avg_treatment_cost
      aggregation: AVG
      source: treatment_cost
      description: "Average cost per visit"
      unit: USD
      format: "$#,##0.00"

  dimensions:
    - name: blood_type
      values: [O+, O-, A+, A-, B+, B-, AB+, AB-]
      phi: false

    - name: diagnosis
      values: free_text
      phi: false

    - name: insurance_provider
      values: [Blue Cross, Aetna, UnitedHealth, Cigna, Humana, Kaiser]
      phi: false

    - name: state
      values: US_STATES
      phi: true
      sensitivity: MEDIUM

    - name: city
      values: free_text
      phi: true
      sensitivity: MEDIUM

  temporal:
    - name: visit_date
      grain: day
      primary: true
      phi: true
      sensitivity: HIGH

    - name: dob
      grain: day
      primary: false
      phi: true
      sensitivity: HIGH
      usage: age_calculations_only

  hierarchies:
    - name: geography
      levels: [state, city, zip]

    - name: diagnosis_category
      levels: [diagnosis]
      note: "To be mapped to ICD-10 in future"
```

## Default Values Summary

### ✅ Automatically Applied

| Category | Setting | Default Value | Source |
|----------|---------|---------------|--------|
| KMS Encryption | Key Alias | alias/hipaa-phi-key | HIPAA regulation |
| KMS Rotation | Frequency | Annual | HIPAA best practice |
| Audit Retention | Days | 2555 (7 years) | HIPAA regulation |
| Staging Retention | Days | 2555 (7 years) | HIPAA regulation |
| Publish Retention | Days | 2555 (7 years) | HIPAA regulation |
| Landing Retention | Days | 90 | Platform default |
| Access Control | Method | Tag-based (TBAC) | HIPAA minimum necessary |
| PHI Masking | SSN | SHA-256 hash | HIPAA de-identification |
| PHI Masking | Email | mask_email | HIPAA de-identification |
| PHI Masking | Phone | mask_partial | HIPAA de-identification |
| PHI Masking | Name | SHA-256 hash | HIPAA de-identification |
| PHI Masking | MRN | tokenize | HIPAA de-identification |
| Quality Threshold | Completeness | 100% | HIPAA data integrity |
| Quality Threshold | Uniqueness | 100% | Platform default |
| Quality Threshold | PHI Encryption | 100% | HIPAA requirement |
| Quality Threshold | PHI Tagged | 100% | HIPAA requirement |
| Schedule | Frequency | Daily 2AM UTC | Platform default |
| SLA | Duration | 2 hours | Platform default |
| Retries | Max Attempts | 3 | Platform default |
| Notification | Method | Email + Slack | Platform default |

### 📝 User-Specified (Non-Default)

| Category | Setting | User Value | Reason |
|----------|---------|------------|--------|
| Data Domain | Domain | Healthcare | User-specified |
| Data Steward | Owner | Healthcare Operations Team | User-specified |
| Failure Email | Address | healthcare-ops-team@hospital.com | User-specified |
| Source Format | Format | CSV | From existing data |
| Source Location | Bucket | s3://prod-data-lake/raw/healthcare/patients/ | User-specified |

## Next Steps

### Phase 0: Health Check & Auto-Detect
- ✅ Sample data available at `workloads/healthcare_patients/sample_data/patients.csv`
- ⏳ Verify AWS resources (S3 buckets, KMS keys, IAM roles, Glue databases, LF-Tags, MWAA)
- ⏳ Verify MCP servers (glue-athena, lakeformation, iam, pii-detection)

### Phase 1: Discovery
- ⏳ Confirm HIPAA regulation selection
- ⏳ Load HIPAA controls from `prompts/data-onboarding-agent/regulation/hipaa.md`
- ⏳ Validate source schema against sample data

### Phase 2: Validation & Deduplication
- ⏳ Scan `workloads/*/config/source.yaml` for duplicate sources
- ⏳ Confirm no overlap with existing workloads

### Phase 3: Profiling
- ⏳ Run PII detection on sample data (automatic via `shared/utils/pii_detection_and_tagging.py`)
- ⏳ Verify PHI classification matches HIPAA categories
- ⏳ Present metadata to human for confirmation

### Phase 4: Generate Artifacts
- ⏳ Spawn Metadata Agent → generate config files
- ⏳ Spawn Transformation Agent → generate ETL scripts with PII masking
- ⏳ Spawn Quality Agent → generate HIPAA compliance checks
- ⏳ Spawn Orchestration DAG Agent → generate Airflow DAG with audit logging

### Phase 5: Deploy to AWS
- ⏳ Create KMS key `alias/hipaa-phi-key` if not exists
- ⏳ Upload scripts to S3
- ⏳ Register Iceberg tables in Glue Catalog
- ⏳ Apply LF-Tags to all PHI columns
- ⏳ Grant TBAC permissions (Admin, Provider, Billing, Analyst, Dashboard User roles)
- ⏳ Deploy DAG to MWAA
- ⏳ Verify HIPAA controls (7 smoke tests)

## Expected Artifacts

```
workloads/healthcare_patients/
├── config/
│   ├── source.yaml
│   ├── semantic.yaml
│   ├── transformations.yaml
│   ├── quality_rules.yaml  # With HIPAA compliance rules
│   └── schedule.yaml
├── scripts/
│   ├── extract/
│   │   └── landing_to_s3.py
│   ├── transform/
│   │   ├── staging_clean.py  # With PII masking
│   │   └── publish_star_schema.py  # With de-identification
│   └── quality/
│       └── run_checks.py  # With HIPAA checks
├── dags/
│   └── healthcare_patients_pipeline.py  # With audit logging
├── tests/
│   ├── unit/
│   │   ├── test_transformations.py
│   │   └── test_quality_rules.py
│   └── integration/
│       ├── test_pipeline_end_to_end.py
│       └── test_hipaa_compliance.py  # HIPAA-specific tests
├── deploy_to_aws.py
├── README.md  # With HIPAA BAA documentation
└── ONBOARDING_SPEC.md  # This file
```

## HIPAA Verification Checklist

Post-deployment smoke tests (from `prompts/data-onboarding-agent/regulation/hipaa.md`):

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

- Main onboarding prompt: `prompts/data-onboarding-agent/03-onboard-build-pipeline.md`
- HIPAA regulation controls: `prompts/data-onboarding-agent/regulation/hipaa.md`
- PII detection utility: `shared/utils/pii_detection_and_tagging.py`
- Sample data: `workloads/healthcare_patients/sample_data/patients.csv`
- Governance framework: `docs/governance-framework.md` (lines 140-165)
