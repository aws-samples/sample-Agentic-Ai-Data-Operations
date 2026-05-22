# Claims Pipeline

HIPAA-compliant healthcare claims data pipeline: Bronze → Silver → Gold.

## Source

- **File**: `demo/sample_data/claims.csv`
- **Format**: CSV, 31 columns
- **Production**: `s3://prod-data-lake/raw/healthcare/claims/`

## Pipeline

| Zone | Table | Format | Quality Gate |
|------|-------|--------|--------------|
| Bronze | Raw CSV (immutable) | CSV | None |
| Silver | `claims_db.silver_claims` | Iceberg | >= 0.80 |
| Gold | `claims_db.gold_claims_analytical` | Iceberg (flat denormalized) | >= 0.95 |

## Key Rules

- **PK**: `claim_id`
- **Dedup**: By `claim_id`, keep latest by `submission_date`
- **Null handling**: Drop rows where `claim_id` is null only
- **PII (HIPAA)**: SSN hashed, names hashed, email masked, phone masked. Address kept with LF-Tag enforcement.
- **Schedule**: Daily 9:00 AM AEST (`0 23 * * *` UTC)

## PHI Columns (HIPAA Protected)

`member_first_name`, `member_last_name`, `member_dob`, `member_ssn`, `member_email`, `member_phone`, `member_address`, `member_city`, `member_state`, `member_zip`

## Derived Columns (Gold)

- `member_age` — years from DOB
- `days_to_submission` — days between service and submission
- `payer_coverage_pct` — paid/billed percentage
- `claim_amount_tier` — Low/Medium/High
- `member_age_group` — Under 18/18-34/35-49/50-64/65+

## Running Locally

```bash
python3 workloads/claims/scripts/transform/bronze_to_silver_claims.py \
  --local --bronze_path demo/sample_data/claims.csv \
  --silver_path /tmp/data-lake/silver/claims/claims.parquet

python3 workloads/claims/scripts/transform/silver_to_gold_claims.py \
  --local --silver_path /tmp/data-lake/silver/claims/claims.parquet \
  --gold_path /tmp/data-lake/gold/claims/claims_analytical.parquet
```
