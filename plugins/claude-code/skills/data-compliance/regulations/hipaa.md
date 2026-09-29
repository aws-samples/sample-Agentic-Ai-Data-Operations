# HIPAA — control block (illustrative, not legal advice). COMPLIANCE-CRITICAL → build with Opus.

Apply to any workload onboarded with `HIPAA`.

## Silver
- **PHI masking**: mask/redact the 18 HIPAA identifiers (name, MRN, dates finer than year,
  addresses, SSN, etc.). Pseudonymize where linkage is needed via keyed hash + KMS.
- Enforce minimum-necessary: carry only PHI columns required for the Gold purpose.

## Gold
- **PHI suppression**: no direct PHI in Gold. Expose de-identified/aggregated measures only.
- Apply date-shifting or generalization for temporal fields where needed.

## Quality
- Validate identifier formats; quarantine malformed PHI. Block promotion on PHI-leak checks.

## Retention & access
- Enforce retention per policy; zone-scoped KMS CMKs; least-privilege access to PHI columns.

## Audit
- Full processing-metadata logging; confirm audit logging active after deploy.
