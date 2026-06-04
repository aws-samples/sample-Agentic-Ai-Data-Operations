# Blockchain Index Onboarding Prompt (AML / OFAC / Travel Rule)

## Prompt to paste

Onboard blockchain transaction data from s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/eth_transactions/
into Silver with dedup on (block_number, transaction_hash, log_index) and not-null policy on
block_number, transaction_hash, block_timestamp, and from_address, and into a flat denormalized
Gold Iceberg table aggregated daily-per-address with derived measures (total_value_usd, tx_count,
gas_spent_eth, mev_flag, sanctions_hit_flag, counterparty_diversity_score, wallet_age_days).

Run every 2 hours via Managed Airflow on AWS, with chain reorg handling (re-process last 12 blocks
each run to absorb reorgs). Apply AML controls: tag any address matching the OFAC SDN list (refresh
daily from Treasury), pseudonymize wallet labels in Silver via deterministic HMAC-SHA256 (key in KMS),
and in Gold expose only the first/last 4 chars of addresses for non-compliance roles. Log Travel
Rule metadata (originator, beneficiary, transfer amount in USD at tx time) for any transfer
>= $3,000 USD equivalent. Maintain an immutable Bronze of raw RPC payloads for forensic replay.

I'm open to suggestions on:
  - Additional data quality rules (e.g., block_timestamp monotonicity within a block,
    gas_used <= gas_limit, value/gas sanity bounds, from_address != to_address for transfers,
    contract-creation tx validation, log_index uniqueness within tx, ERC-20/721/1155 event
    signature validation)
  - Additional Silver/Gold transformations (e.g., decode known contract ABIs into typed event
    tables, USD price enrichment via daily oracle snapshots, address clustering heuristics,
    MEV pattern detection — sandwich/arbitrage/liquidation, bridge transaction detection,
    stablecoin flow tagging, smart-contract age and verified-source enrichment, SCD on
    contract ownership/proxy upgrades, derived KPIs like daily active addresses, gas-weighted
    top contracts, sanctions exposure score)

Please profile the data first (one block range sample), then propose your recommended quality
thresholds and transforms before generating any code.

---

## Readiness Verification (run before pasting the prompt)

Account: `<ACCOUNT_ID>` | Region: `us-east-1` | Workload: `blockchain_index`

```bash
# Source prefix (partitioned dt=YYYY-MM-DD, JSON lines)
aws s3 ls s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/eth_transactions/

# Zone buckets
for B in adop-workshop-bronze-<ACCOUNT_ID> \
         adop-workshop-silver-<ACCOUNT_ID> \
         adop-workshop-gold-<ACCOUNT_ID> \
         adop-workshop-audit-<ACCOUNT_ID> \
         adop-workshop-mwaa-dags-<ACCOUNT_ID>; do
  aws s3api head-bucket --bucket $B 2>/dev/null && echo "OK $B" || echo "MISSING $B"
done

# AML KMS key (used for HMAC pseudonymization + table encryption)
aws kms describe-key --key-id alias/blockchain-aml-key --region us-east-1 \
  --query 'KeyMetadata.{Id:KeyId,Rotation:KeyState}' --output table

# AML IAM roles
for R in ComplianceOfficerRole AMLAnalystRole BlockchainResearcherRole DashboardUserRole; do
  aws iam get-role --role-name $R --query 'Role.Arn' --output text 2>/dev/null \
    && echo "OK $R" || echo "MISSING $R"
done

# LF-Tags (sanctions/PII tags must exist before TBAC grants)
aws lakeformation list-lf-tags --region us-east-1 \
  --query 'LFTags[?TagKey==`Sanctions_Risk` || TagKey==`PII_Classification` || TagKey==`Data_Sensitivity`].TagKey' \
  --output text

# OFAC SDN list refresh job (daily) — verify reference dataset present
aws s3 ls s3://adop-workshop-bronze-<ACCOUNT_ID>/reference/ofac_sdn/ \
  --recursive --summarize | tail -5

# CloudTrail (BSA audit trail)
aws cloudtrail describe-trails --region us-east-1 \
  --query 'trailList[].Name' --output text

# Audit bucket Object Lock (BSA 5-year + sanctions 7-year immutability)
aws s3api get-object-lock-configuration --bucket adop-workshop-audit-<ACCOUNT_ID> \
  --query 'ObjectLockConfiguration.ObjectLockEnabled' --output text

# MWAA env
aws mwaa list-environments --region us-east-1 --query 'Environments' --output text

# No workload-name conflict
test -d workloads/blockchain_index && echo "CONFLICT" || echo "OK no workloads/blockchain_index"
```

All lines must print `OK` / a non-empty value. If anything is missing, run
`prompts/environment-setup-agent/01-setup-aws-infrastructure.md` first.

---

## Confirmed inputs (already locked in)

- Source: `s3://adop-workshop-landing-<ACCOUNT_ID>/demo_landing/eth_transactions/` (JSON lines, partitioned by `dt=YYYY-MM-DD`)
- Zone targets: Bronze (raw JSON, immutable), Silver (Iceberg), Gold (flat denormalized Iceberg)
- PK / dedup: `(block_number, transaction_hash, log_index)`
- Not-null: `block_number`, `transaction_hash`, `block_timestamp`, `from_address`
- Schedule: `0 */2 * * *` UTC (every 2 hours)
- Reorg policy: re-process last 12 blocks per run to absorb chain reorganizations
- Regulation: AML/BSA + OFAC sanctions screening + FinCEN Travel Rule (>= $3,000 USD)
- Retention: 5 years for transaction data (BSA), 7 years for sanctions screening audit logs, indefinite for flagged-address registry
- KMS key: `alias/blockchain-aml-key`
- Roles: `ComplianceOfficerRole`, `AMLAnalystRole`, `BlockchainResearcherRole`, `DashboardUserRole`

## Items the agent will ask you to confirm at Phase 1

- Address columns to pseudonymize in Silver (likely: `from_address`, `to_address`, `contract_address`, decoded `to`/`from` in ERC-20 events)
- USD price oracle source (Chainlink daily snapshot? CoinGecko? on-chain TWAP?) and fallback policy when price is missing
- OFAC SDN refresh cadence (daily default) and source path/URL (Treasury XML feed)
- Travel Rule threshold currency conversion timestamp (price at tx time vs. day-close)
- Quality thresholds per dimension (or `use defaults`)
- Contract ABIs to decode (top-N by tx volume, or specific list — USDC/USDT/DAI/WETH/Uniswap/etc.)
- MEV detection scope (sandwich only, or full set — sandwich/arbitrage/liquidation/JIT)
- Ontology opt-in (yes/no) and use cases if yes (e.g., counterparty graph, sanctions exposure lineage, contract upgrade history)
