---
name: Compliance context
description: HIPAA compliance, PHI classification across 4 sensitivity levels, 7-year audit retention
type: project
---

## Regulation

- **HIPAA** (Health Insurance Portability and Accountability Act)
- **BAA required**: Yes — Business Associate Agreement with all data processors
- **Breach notification**: 60 days
- **Minimum necessary**: Only grant access to PHI columns required for the role

## PHI Classification by Sensitivity

### CRITICAL (strongest protection)
- **ssn**: SHA-256 hash — irreversible, never stored in plaintext after Bronze
- **medical_record_number**: Tokenize — reversible lookup via secure token vault

### HIGH (strong protection)
- **patient_name**: SHA-256 hash in Silver
- **dob**: Convert to age calculation (drop raw date in Silver)
- **email**: Mask in Silver (show domain only)
- **visit_date**: Retained but access-controlled via LF-Tags

### MEDIUM (standard protection)
- **phone**: Mask last 4 digits
- **address**: Mask street number
- **city**, **state**, **zip**: Access-controlled but not masked (needed for geographic analysis)

### LOW (minimal protection, non-PHI)
- **patient_id**: Identifier, not PHI itself
- **blood_type**: Clinical attribute, not identifying
- **diagnosis**: Sensitive but not PHI under HIPAA Safe Harbor
- **treatment_cost**: Financial, not identifying
- **insurance_provider**: Business attribute

## Encryption

- **KMS key**: alias/hipaa-phi-key (all zones: landing, staging, publish)
- **Algorithm**: AES-256 at rest, TLS 1.3 in transit
- **Key rotation**: Annual, automatic
- **Catalog metadata**: alias/catalog-metadata-key (separate key)

## Audit and Retention

- **Audit retention**: 7 years (2555 days)
- **S3 Object Lock**: Enabled on audit log bucket — immutable audit trail
- **CloudTrail events tracked**: GetDataAccess, AddLFTagsToResource, GrantPermissions, RevokePermissions
- **PHI must never appear in logs** — scan for SSN patterns (XXX-XX-XXXX) as validation

## Quality Gates

| Gate | Score | Critical Failures | HIPAA Checks |
|---|---|---|---|
| Landing -> Staging | 0.80 | 0 | n/a |
| Staging -> Publish | 0.95 | 0 | All must pass |
| Publish -> Dashboard | 0.98 | 0 | n/a |

## Role-Based Access (LF-Tags)

- **Admin**: Full access to all columns including CRITICAL PHI
- **Provider**: Access to HIGH/MEDIUM/LOW but NOT CRITICAL (no SSN, no MRN)
- **Billing**: Access to treatment_cost, insurance_provider, patient_id only
- **Analyst**: Access to LOW sensitivity columns only (aggregated views)
