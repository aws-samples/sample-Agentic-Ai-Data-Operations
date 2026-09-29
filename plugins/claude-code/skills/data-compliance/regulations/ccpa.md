# CCPA — control block (illustrative, not legal advice)

Apply to any workload onboarded with `CCPA`.

## Silver
- Pseudonymize personal information (PI); tag columns that constitute PI under CCPA.
- Honor opt-out: filter rows for consumers who have opted out of sale/sharing.

## Gold
- Aggregate/derive only for PI; suppress raw identifiers.

## Quality
- Validate PI formats; quarantine malformed rows.

## Retention & rights
- Support **right to delete** and **right to know** via a subject-keyed erasure/export hook.
- Enforce a documented retention window per business purpose.

## Audit
- Log processing metadata and opt-out enforcement decisions.
