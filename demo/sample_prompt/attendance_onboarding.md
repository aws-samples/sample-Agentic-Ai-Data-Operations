# Attendance Onboarding Prompt (GDPR)

## Prompt to paste

Onboard attendance data from s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/attendance.csv
into Silver with dedup on (employee_id, check_in) and not-null policy on employee_id and check_in,
and into a flat denormalized Gold Iceberg table aggregated daily-per-employee with derived measures
(hours_worked_clean, attendance_rate, late_arrival_flag, overtime_hours, absence_category).

Run daily at 03:00 UTC. Apply GDPR controls: hash/pseudonymize email and full_name in Silver,
suppress full_name and mask email domain in Gold, honor 365-day retention, and log lawful-basis
metadata for processing.

I'm open to suggestions on:
  - Additional data quality rules (e.g., check_out >= check_in, hours_worked sanity bounds,
    status enum validation, manager_id referential checks)
  - Additional Silver/Gold transformations (e.g., shift bucketing, location normalization,
    SCD on department/manager changes, derived KPIs)

Please profile the data first, then propose your recommended quality thresholds and transforms
before generating any code.

---

## Readiness Verification (run before pasting the prompt)

Account: `<ACCOUNT_ID>` | Region: `us-east-1` | Workload: `attendance`

```bash
# Source file
aws s3 ls s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/attendance.csv

# Zone buckets
for B in adop-workshop-bronze-<ACCOUNT_ID> \
         adop-workshop-silver-<ACCOUNT_ID> \
         adop-workshop-gold-<ACCOUNT_ID> \
         adop-workshop-audit-<ACCOUNT_ID> \
         adop-workshop-mwaa-dags-<ACCOUNT_ID>; do
  aws s3api head-bucket --bucket $B 2>/dev/null && echo "OK $B" || echo "MISSING $B"
done

# GDPR KMS key
aws kms describe-key --key-id alias/attendance-gdpr-key --region us-east-1 \
  --query 'KeyMetadata.{Id:KeyId,Rotation:KeyState}' --output table

# GDPR IAM roles
for R in DPORole DataStewardRole AnalystRole DashboardUserRole; do
  aws iam get-role --role-name $R --query 'Role.Arn' --output text 2>/dev/null \
    && echo "OK $R" || echo "MISSING $R"
done

# LF-Tags
aws lakeformation list-lf-tags --region us-east-1 \
  --query 'LFTags[?TagKey==`PII_Classification` || TagKey==`PII_Type` || TagKey==`Data_Sensitivity`].TagKey' \
  --output text

# CloudTrail
aws cloudtrail describe-trails --region us-east-1 \
  --query 'trailList[].Name' --output text

# Audit bucket Object Lock (GDPR audit immutability)
aws s3api get-object-lock-configuration --bucket adop-workshop-audit-<ACCOUNT_ID> \
  --query 'ObjectLockConfiguration.ObjectLockEnabled' --output text

# MWAA env
aws mwaa list-environments --region us-east-1 --query 'Environments' --output text

# No workload-name conflict
test -d workloads/attendance && echo "CONFLICT" || echo "OK no workloads/attendance"
```

All lines must print `OK` / a non-empty value. If anything is missing, run
`prompts/environment-setup-agent/01-setup-aws-infrastructure.md` first.

---

## Confirmed inputs (already locked in)

- Source: `s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/attendance.csv`
- Zone targets: Bronze (raw CSV), Silver (Iceberg), Gold (flat denormalized Iceberg)
- PK / dedup: `(employee_id, check_in)`
- Not-null: `employee_id`, `check_in`
- Schedule: `0 3 * * *` UTC
- Regulation: GDPR
- Retention: 365 days for personal data; 7 years for audit logs
- KMS key: `alias/attendance-gdpr-key`
- Roles: `DPORole`, `DataStewardRole`, `AnalystRole`, `DashboardUserRole`

## Items the agent will ask you to confirm at Phase 1

- PII column list (likely candidates: `full_name`, `email`; possibly `manager_id`)
- Lawful basis (consent / contract / legitimate interest / legal obligation)
- Quality thresholds per dimension (or `use defaults`)
- Specific Silver/Gold transformations beyond the suggested ones
- Ontology opt-in (yes/no) and use cases if yes
