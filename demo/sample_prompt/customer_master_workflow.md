# Customer Master Workflow Onboarding (CCPA + GDPR)

## Prompt to paste

/onboard-workflow CCPA GDPR

Onboard customer master data from s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/customer_master.csv
into Silver with dedup on (customer_id) and not-null policy on customer_id, email, and last_name,
and into a Star Schema Gold with a dim_customer dimension table for downstream BI/analytics.

Run daily at 02:00 UTC. Apply CCPA + GDPR dual-compliance controls:
- Silver: hash SSN (irreversible SHA-256), pseudonymize email and phone, encrypt date_of_birth and address with KMS, retain full_name for join resolution but tag as PII
- Gold: suppress SSN entirely, mask email to domain-only (***@domain.com), redact address to city+state+zip only, suppress phone
- Honor 730-day CCPA retention (personal data), 365-day GDPR retention (whichever is stricter per field), 7 years for audit logs
- Track opt-out/consent status per customer, support right-to-delete and right-to-know requests
- Log lawful-basis metadata (contract for account management, consent for marketing)

I'm open to suggestions on:
  - Additional data quality rules (e.g., email format validation, SSN format check,
    zip_code length/format, credit_score range 300-850, annual_income > 0,
    account_open_date <= today, date_of_birth reasonable bounds)
  - Additional Silver/Gold transformations (e.g., age derivation, income bucketing,
    geographic region assignment, customer tenure calculation, risk score normalization,
    SCD Type 2 on risk_profile/employment_status/address changes)
  - Customer segmentation derived columns for Gold (e.g., wealth_tier, lifecycle_stage,
    geographic_region, employment_category)

---

## How this differs from the non-workflow prompt

The `/onboard-workflow CCPA GDPR` prefix triggers the Dynamic Workflow skill instead of
the standard sequential onboarding. The differences:

| Aspect | Standard (`customer_master_onboarding.md`) | Workflow (this file) |
|--------|---------------------------------------------|----------------------|
| Execution | Sequential Agent calls (one at a time) | Parallel sub-agents via Workflow tool |
| Phase 4 | Metadata → Transform → Quality → DAG (sequential) | [Metadata \| Quality] → Transform → DAG (parallel stage 1) |
| Model routing | Same model for everything | Haiku (health/validate), Sonnet (build), Opus (adversarial/verify) |
| Progress | No persistence — lost on disconnect | Persisted per phase — resumable |
| Wall clock | ~30 min for full pipeline | ~15-20 min (parallelized) |
| Token cost | 1x baseline | 3-5x (more agents, but faster) |

## What stays the same

- Phase 1 discovery questions are still asked (the workflow does NOT skip them)
- The codegen renderer still produces all `.py` scripts (deterministic, drift-validated)
- All hooks still enforce (discovery gate, template codegen, logging)
- Quality gates still block zone promotion
- Post-deployment verification still runs 7 checks

---

## Readiness Status (last checked: 2026-05-27)

| Check | Status |
|-------|--------|
| Source file in S3 | **OK** — uploaded 2026-05-27 (9,117 bytes, 50 rows) |
| Zone buckets (5) | **OK** — bronze, silver, gold, audit, mwaa-dags |
| KMS key `alias/customer-master-pii-key` | **OK** — `563b7381-a137-4381-8c7f-9474fd39d682`, rotation enabled |
| DPORole | **OK** — exists |
| DataStewardRole | **OK** — exists |
| AnalystRole | **OK** — exists |
| PrivacyTeamRole | **MISSING** — needs creation (CCPA opt-out handling) |
| MarketingRole | **MISSING** — needs creation (restricted PII access for marketing) |
| LF-Tags (PII) | **OK** — PII_Classification, PII_Type, Data_Sensitivity |
| CloudTrail | **OK** — trail active |
| Audit bucket Object Lock | **OK** — enabled |
| MWAA | **OK** — 2 environments available |
| Workload conflict | **OK** — no existing workloads/customer_master |

### Prerequisites still needed

1. **Create `PrivacyTeamRole`** — handles CCPA opt-out requests, right-to-delete, right-to-know
2. **Create `MarketingRole`** — restricted access (no SSN, no raw email, no address details)

```bash
aws iam create-role --role-name PrivacyTeamRole \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lakeformation.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
  --description "CCPA Privacy Team - manages opt-out, deletion, and access requests"

aws iam create-role --role-name MarketingRole \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lakeformation.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
  --description "Marketing - restricted PII access (no SSN, no raw contact info)"
```

---

## Readiness Verification (run before pasting the prompt)

Account: `<ACCOUNT_ID>` | Region: `us-east-1` | Workload: `customer_master`

```bash
# Source file
aws s3 ls s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/customer_master.csv

# Zone buckets
for B in adop-workshop-bronze-<ACCOUNT_ID> \
         adop-workshop-silver-<ACCOUNT_ID> \
         adop-workshop-gold-<ACCOUNT_ID> \
         adop-workshop-audit-<ACCOUNT_ID> \
         adop-workshop-mwaa-dags-<ACCOUNT_ID>; do
  aws s3api head-bucket --bucket $B 2>/dev/null && echo "OK $B" || echo "MISSING $B"
done

# KMS key (dual-compliance)
aws kms describe-key --key-id alias/customer-master-pii-key --region us-east-1 \
  --query 'KeyMetadata.{Id:KeyId,Rotation:KeyState}' --output table

# IAM roles (CCPA + GDPR)
for R in DPORole PrivacyTeamRole DataStewardRole AnalystRole MarketingRole; do
  aws iam get-role --role-name $R --query 'Role.Arn' --output text 2>/dev/null \
    && echo "OK $R" || echo "MISSING $R"
done

# LF-Tags
aws lakeformation list-lf-tags --region us-east-1 \
  --query 'LFTags[?TagKey==`PII_Classification` || TagKey==`PII_Type` || TagKey==`Data_Sensitivity`].TagKey' \
  --output text

# MCP servers (required for workflow)
claude mcp list 2>/dev/null || echo "Run: claude mcp list"

# No workload-name conflict
test -d workloads/customer_master && echo "CONFLICT" || echo "OK no workloads/customer_master"
```

---

## Confirmed inputs (already locked in)

- Source: `s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/customer_master.csv`
- Zone targets: Bronze (raw CSV), Silver (Iceberg), Gold (Star Schema — dim_customer)
- PK / dedup: `(customer_id)`
- Not-null: `customer_id`, `email`, `last_name`
- Schedule: `0 2 * * *` UTC
- Regulation: CCPA + GDPR (dual-compliance, apply stricter rule per field)
- Retention: 730 days CCPA (personal data), 365 days GDPR (EU subjects), 7 years audit logs
- KMS key: `alias/customer-master-pii-key`
- Roles: `DPORole`, `PrivacyTeamRole`, `DataStewardRole`, `AnalystRole`, `MarketingRole`

## Items the agent will ask you to confirm at Phase 1

Even though the prompt provides most answers, the workflow skill will still confirm:
- PII column list and sensitivity levels
- Lawful basis per processing purpose
- Whether to apply SCD Type 2 on risk_profile, employment_status, address
- Quality thresholds (or "use defaults")
- Gold segmentation columns
- Ontology opt-in (yes/no)
