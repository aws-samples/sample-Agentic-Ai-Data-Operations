# Regulation-Specific Prompt Library

## Purpose

Self-contained compliance prompts for each supported regulation. Each prompt contains the specific controls, YAML config, quality rules, masking, LF-Tag, and audit requirements for that regulation.

## When to Use

These prompts are **NOT applied by default**. Load them ONLY when:

1. User selects a regulation during Phase 1 discovery (section 6a)
2. User asks "does this comply with {REGULATION}?"
3. Workload config has `compliance: [{REGULATION}]` in quality_rules.yaml

When a regulation is selected, its prompt is **mandatory** — apply ALL controls listed.

## Available Regulations

| File | Regulation | Key Focus |
|------|-----------|-----------|
| [gdpr.md](gdpr.md) | GDPR | Right to erasure, consent, data minimization, 365-day retention |
| [ccpa.md](ccpa.md) | CCPA | Right to know/delete, opt-out tracking, data lineage |
| [hipaa.md](hipaa.md) | HIPAA | PHI protection, BAA, minimum necessary, KMS encryption |
| [sox.md](sox.md) | SOX | Financial integrity, 0.95+ quality threshold, 7-year audit |
| [pci-dss.md](pci-dss.md) | PCI DSS | Cardholder data masking, restricted access, Luhn validation |

## How to Pick

| If the data contains... | Load... |
|------------------------|---------|
| EU/EEA personal data | GDPR |
| California consumer data | CCPA |
| Patient/health records | HIPAA |
| Financial statements, accounting | SOX |
| Credit card / payment data | PCI DSS |

Multiple regulations can apply simultaneously (e.g., GDPR + CCPA for a global customer dataset).

## Shared Infrastructure

All regulation prompts build on the same shared utilities:

- **PII Detection**: `shared/utils/pii_detection_and_tagging.py` (12 PII types, AI-driven)
- **Cedar Policies**: `shared/policies/guardrails/sec_003_pii_masking.cedar`
- **LF-Tags**: `PII_Classification`, `PII_Type`, `Data_Sensitivity`
- **Audit**: CloudTrail for all Lake Formation operations

## Related Documentation

- `docs/governance-framework.md` — Full governance architecture and control matrices
- `docs/governance-integration-example.md` — End-to-end GDPR+CCPA onboarding example
- `SKILLS.md` section 6a — Discovery phase compliance questions
- `CLAUDE.md` Security Rule 5 — Regulatory compliance requirement
