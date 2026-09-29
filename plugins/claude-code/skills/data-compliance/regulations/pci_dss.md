# PCI DSS — control block (illustrative, not legal advice). COMPLIANCE-CRITICAL → build with Opus.

Apply to any workload onboarded with `PCI` / `PCI DSS`.

## Silver
- **Tokenize PAN** (primary account number); never store PAN in the clear.
- **Drop CVV/CVC** entirely — must never be persisted.
- Mask displayed card numbers to last 4 (`****-****-****-1234`).

## Gold
- No PAN/CVV in Gold. Expose tokenized/aggregated payment measures only.

## Quality
- **Luhn check** on card numbers as a validity rule; quarantine failures.
- Validate expiry formats; flag anomalous transaction amounts.

## Retention & access
- Minimize cardholder-data retention; zone-scoped KMS; least-privilege access.

## Audit
- Log processing metadata; confirm audit logging active after deploy.
