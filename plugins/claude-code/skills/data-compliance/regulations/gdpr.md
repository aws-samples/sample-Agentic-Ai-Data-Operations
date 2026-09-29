# GDPR — control block (illustrative, not legal advice)

Apply to any workload onboarded with `GDPR`.

## Silver
- Pseudonymize direct identifiers (name, email, phone) via keyed hash; keep a reversible
  mapping only in a KMS-encrypted, access-controlled store if re-identification is required.
- Consent-based filter: drop/withhold rows lacking a valid consent flag for the processing purpose.

## Gold
- Expose only aggregated/derived measures for personal data; suppress raw identifiers.
- No direct identifiers in Gold unless a lawful basis is documented in `semantic.yaml`.

## Quality
- Validate email/phone formats; quarantine malformed PII rather than dropping silently.

## Retention & rights
- Default retention: 365 days (override per purpose). Enforce a retention/expiry policy.
- **Right to erasure**: implement an erasure hook keyed on the subject identifier that purges
  Bronze-derived Silver/Gold rows and the pseudonym mapping.

## Audit
- Log processing metadata (purpose, timestamp, dataset, controls applied).
