# SOX — control block (illustrative, not legal advice). COMPLIANCE-CRITICAL → build with Opus.

Apply to any workload onboarded with `SOX` (financial-reporting integrity focus).

## Silver
- Immutable, auditable lineage for every financial record; no silent mutation.
- Segregation-of-duties: the pipeline role cannot both alter data and approve promotion.

## Gold
- Reconciliation checks: derived financial measures must tie back to source totals.
- Change control: schema/logic changes require reviewed, versioned artifacts.

## Quality
- Completeness ≥ 99% for financial columns; balance/reconciliation invariants BLOCK on failure.

## Retention & audit
- Long retention per policy; tamper-evident audit trail of every transform and approval.
- Confirm audit logging active after deploy.
