# Trade Data Onboarding Prompt (SOX + PCI DSS)

## Prompt to paste

Onboard trade execution data from s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/trade_data.csv
into Silver with dedup on (trade_id) and not-null policy on trade_id, customer_id, trade_date, symbol,
quantity, and price, and into a Star Schema Gold with fact_trades (measures) + dim_security,
dim_customer, dim_broker, dim_date dimensions for financial reporting and compliance analytics.

Run every 30 minutes during market hours (13:30-21:00 UTC Mon-Fri) and once daily at 01:00 UTC
for overnight settlement reconciliation. Apply SOX + PCI DSS controls:
- Bronze: immutable raw trade records (no modification after ingestion), full audit trail
- Silver: validate trade amounts (quantity * price = total_amount), reconcile commission + fees = net_amount delta, flag settlement date anomalies, tag customer_id as indirect PII (FK to customer_master)
- Gold: financial-grade accuracy (0.95+ quality gate), immutable fact records for SOX audit trail, no retroactive changes without audit entry
- SOX: segregation of duties (trade execution vs. audit roles), 7-year retention for all financial records, quarterly reconciliation checkpoints
- PCI DSS: if any payment instrument data appears, tokenize immediately; validate no CVV/PAN leakage

I'm open to suggestions on:
  - Additional data quality rules (e.g., settlement_date >= trade_date, settlement T+2 rule validation,
    price > 0, quantity > 0 for BUY / quantity validation for SELL, commission as % of total_amount bounds,
    exchange enum validation, order_type enum validation, status state machine validation,
    cross-reference customer_id against customer_master, duplicate trade detection within time window)
  - Additional Silver/Gold transformations (e.g., trade_value_usd normalization, intraday P&L calculation,
    rolling VWAP per symbol, position netting, daily portfolio NAV, sector/industry enrichment from security master,
    trade velocity anomaly detection, wash sale flagging, concentration risk metrics)
  - Risk and compliance derived measures for Gold (e.g., position_concentration_pct, daily_var,
    trade_velocity_score, unusual_activity_flag, settlement_risk_score)

Please profile the data first, then propose your recommended quality thresholds and transforms
before generating any code.

---

## Readiness Status (last checked: 2026-05-27)

| Check | Status |
|-------|--------|
| Source file in S3 | **OK** — uploaded 2026-05-27 (7,708 bytes, 50 rows) |
| Zone buckets (5) | **OK** — bronze, silver, gold, audit, mwaa-dags |
| KMS key `alias/trade-data-sox-key` | **OK** — `0fcf6bc2-e141-4ac5-a8b9-1ce21aea28e1`, rotation enabled |
| AuditorRole | **MISSING** — needs creation (SOX read-only audit access) |
| FinanceRole | **MISSING** — needs creation (financial reporting access) |
| ComplianceOfficerRole | **MISSING** — needs creation (trade surveillance) |
| TradeOpsRole | **MISSING** — needs creation (trade execution, no audit access) |
| ExternalAuditorRole | **MISSING** — needs creation (quarterly SOX audit, time-bounded) |
| LF-Tags (PII) | **OK** — PII_Classification, PII_Type, Data_Sensitivity |
| LF-Tag `SOX_Classification` | **MISSING** — needs creation (values: Financial_Record, Audit_Trail, Non_SOX) |
| CloudTrail | **OK** — trail active |
| Audit bucket Object Lock | **OK** — enabled (7-year immutability for SOX) |
| MWAA | **OK** — 2 environments available |
| Workload conflict | **OK** — no existing workloads/trade_data |
| Dependency: customer_master | **WARN** — not onboarded yet (FK checks deferred in Gold) |

### Prerequisites still needed

1. **Create 5 IAM roles** for SOX segregation of duties:
2. **Create LF-Tag** `SOX_Classification` for financial data tagging

```bash
# Create SOX/PCI roles
for R in AuditorRole FinanceRole ComplianceOfficerRole TradeOpsRole ExternalAuditorRole; do
  aws iam create-role --role-name $R \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lakeformation.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --description "SOX compliance role: $R"
done

# Create SOX_Classification LF-Tag
aws lakeformation create-lf-tag --region us-east-1 \
  --tag-key SOX_Classification \
  --tag-values '["Financial_Record","Audit_Trail","Non_SOX"]'
```

3. **(Optional)** Onboard `customer_master` first if you want FK validation in Gold

---

## Readiness Verification (run before pasting the prompt)

Account: `<ACCOUNT_ID>` | Region: `us-east-1` | Workload: `trade_data`

```bash
# Source file
aws s3 ls s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/trade_data.csv

# Zone buckets
for B in adop-workshop-bronze-<ACCOUNT_ID> \
         adop-workshop-silver-<ACCOUNT_ID> \
         adop-workshop-gold-<ACCOUNT_ID> \
         adop-workshop-audit-<ACCOUNT_ID> \
         adop-workshop-mwaa-dags-<ACCOUNT_ID>; do
  aws s3api head-bucket --bucket $B 2>/dev/null && echo "OK $B" || echo "MISSING $B"
done

# SOX KMS key
aws kms describe-key --key-id alias/trade-data-sox-key --region us-east-1 \
  --query 'KeyMetadata.{Id:KeyId,Rotation:KeyState}' --output table

# IAM roles (SOX + PCI DSS)
for R in AuditorRole FinanceRole ComplianceOfficerRole TradeOpsRole ExternalAuditorRole; do
  aws iam get-role --role-name $R --query 'Role.Arn' --output text 2>/dev/null \
    && echo "OK $R" || echo "MISSING $R"
done

# LF-Tags
aws lakeformation list-lf-tags --region us-east-1 \
  --query 'LFTags[?TagKey==`PII_Classification` || TagKey==`PII_Type` || TagKey==`Data_Sensitivity` || TagKey==`SOX_Classification`].TagKey' \
  --output text

# CloudTrail
aws cloudtrail describe-trails --region us-east-1 \
  --query 'trailList[].Name' --output text

# Audit bucket Object Lock (SOX immutable audit trail — 7 years)
aws s3api get-object-lock-configuration --bucket adop-workshop-audit-<ACCOUNT_ID> \
  --query 'ObjectLockConfiguration.ObjectLockEnabled' --output text

# MWAA env
aws mwaa list-environments --region us-east-1 --query 'Environments' --output text

# No workload-name conflict
test -d workloads/trade_data && echo "CONFLICT" || echo "OK no workloads/trade_data"

# Dependency: customer_master workload exists (for FK reference)
test -d workloads/customer_master && echo "OK customer_master exists" || echo "WARN customer_master not onboarded yet"
```

All lines must print `OK` / a non-empty value. If anything is missing, run
`prompts/environment-setup-agent/01-setup-aws-infrastructure.md` first.

---

## Confirmed inputs (already locked in)

- Source: `s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/trade_data.csv`
- Zone targets: Bronze (raw CSV), Silver (Iceberg), Gold (Star Schema — fact_trades + dims)
- PK / dedup: `(trade_id)`
- Not-null: `trade_id`, `customer_id`, `trade_date`, `symbol`, `quantity`, `price`
- Schedule: `*/30 13-21 * * 1-5` UTC (market hours) + `0 1 * * *` UTC (overnight reconciliation)
- Regulation: SOX + PCI DSS
- Retention: 7 years for all financial records (SOX), immediate tokenization for payment data (PCI DSS)
- KMS key: `alias/trade-data-sox-key`
- Roles: `AuditorRole`, `FinanceRole`, `ComplianceOfficerRole`, `TradeOpsRole`, `ExternalAuditorRole`

## Data Quality Rules (expected — agent will confirm)

| Rule | Type | Severity | Description |
|------|------|----------|-------------|
| Amount reconciliation | Accuracy | CRITICAL | `quantity * price = total_amount` (tolerance ±$0.01) |
| Net amount check | Accuracy | CRITICAL | `total_amount + commission + fees = net_amount` (for BUY) |
| Settlement date | Validity | HIGH | `settlement_date >= trade_date` |
| T+2 settlement | Validity | WARNING | `settlement_date <= trade_date + 2 business days` |
| Price positivity | Validity | CRITICAL | `price > 0` |
| Quantity positivity | Validity | CRITICAL | `quantity > 0` |
| Status enum | Validity | HIGH | `status IN (Submitted, Pending, Settled, Cancelled, Failed)` |
| Trade type enum | Validity | HIGH | `trade_type IN (BUY, SELL, SHORT, COVER)` |
| Order type enum | Validity | MEDIUM | `order_type IN (Market, Limit, Stop, StopLimit)` |
| Exchange enum | Validity | MEDIUM | `exchange IN (NYSE, NASDAQ, AMEX, CBOE, ...)` |
| Customer FK | Consistency | HIGH | `customer_id EXISTS IN dim_customer` |
| Duplicate window | Uniqueness | HIGH | No same (customer_id, symbol, trade_type, quantity) within 1 minute |

## Gold Star Schema Design (proposed)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GOLD: Star Schema                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐         ┌─────────────────────┐                   │
│  │ dim_security │◄────────┤                     │                   │
│  │  symbol      │         │    fact_trades       │                   │
│  │  name        │         │                     │                   │
│  │  asset_class │         │  trade_id (PK)      │                   │
│  │  exchange    │         │  customer_sk (FK)   │──►┌─────────────┐ │
│  │  sector      │         │  security_sk (FK)   │   │dim_customer │ │
│  └──────────────┘         │  broker_sk (FK)     │   │ customer_id │ │
│                           │  date_sk (FK)       │   │ risk_profile│ │
│  ┌──────────────┐         │                     │   │ account_type│ │
│  │  dim_broker  │◄────────┤  quantity           │   └─────────────┘ │
│  │  broker_id   │         │  price              │                   │
│  │  broker_name │         │  total_amount       │   ┌─────────────┐ │
│  └──────────────┘         │  commission         │   │  dim_date   │ │
│                           │  net_amount         │──►│ trade_date  │ │
│                           │  trade_type         │   │ fiscal_qtr  │ │
│                           │  settlement_risk    │   │ is_eom      │ │
│                           │  concentration_pct  │   └─────────────┘ │
│                           └─────────────────────┘                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Compliance Controls (SOX + PCI DSS)

| Control | Requirement | Implementation |
|---------|-------------|----------------|
| Immutability | SOX: no retroactive changes | Bronze append-only, Gold fact records never updated |
| Audit trail | SOX: who changed what, when | CloudTrail + audit bucket with Object Lock (7-year) |
| Segregation of duties | SOX: trade ops ≠ auditor | LF-Tags TBAC: TradeOpsRole cannot access audit tables |
| Financial accuracy | SOX: 0.95+ quality gate | Amount reconciliation rules block on failure |
| PAN/CVV check | PCI DSS: no card data stored | Automated scan — if found, tokenize or drop immediately |
| Access logging | Both: all queries logged | CloudTrail + Athena query logs retained 7 years |
| Quarterly reconciliation | SOX: periodic validation | Scheduled quarterly full-refresh quality check |

## Items the agent will ask you to confirm at Phase 1

- Whether customer_id should be treated as indirect PII (FK linkage to customer_master)
- Quality thresholds per dimension (proposed: 0.95+ for Accuracy, 0.90+ for others, or `use defaults`)
- Gold schema: confirm Star Schema with proposed dimensions vs. flat denormalized
- Settlement T+2 rule: strict enforcement (CRITICAL) or advisory (WARNING)?
- Risk metrics to include in Gold (concentration_pct, settlement_risk_score, trade_velocity)
- Whether to join/enrich with customer_master data in Gold (adds risk_profile, account_type)
- Ontology opt-in (yes/no) — entities: Trade, Security, Customer, Broker, Portfolio
- If ontology yes: use cases (compliance audit, trade surveillance, NL→SQL for finance team)
