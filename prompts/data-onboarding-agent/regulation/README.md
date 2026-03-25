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

## Prerequisites (Run Before Applying Controls)

**All 5 regulation prompts now include a Prerequisites section** that verifies required AWS resources exist before applying controls:

| What's Checked | Why It Matters |
|----------------|----------------|
| **KMS encryption keys** | Regulation-specific keys (e.g., `alias/hipaa-phi-key`, `alias/pci-cardholder-key`) must exist before encrypting data |
| **IAM roles** | Access control roles (e.g., `DPORole`, `AuditorRole`, `pci_admin_role`) must exist before granting Lake Formation permissions |
| **LF-Tags** | 3 tags (`PII_Classification`, `PII_Type`, `Data_Sensitivity`) must exist before tagging columns |
| **CloudTrail** | Must be enabled to meet audit trail requirements |
| **S3 audit bucket** | Immutable audit log storage (with Object Lock) required for compliance |

**What to do if prerequisites are missing:**

1. Run the environment setup: `prompts/environment-setup-agent/01-setup-aws-infrastructure.md`
2. Or create resources manually using the commands in each regulation prompt's Prerequisites section
3. **Do NOT proceed with onboarding until all prerequisites pass** — deployments will fail at Phase 5 without them

Each regulation prompt includes a "Quick check" bash script to verify all prerequisites in ~10 seconds.

## Related Documentation

- `docs/governance-framework.md` — Full governance architecture and control matrices
- `docs/governance-integration-example.md` — End-to-end GDPR+CCPA onboarding example
- `SKILLS.md` section 6a — Discovery phase compliance questions
- `CLAUDE.md` Security Rule 5 — Regulatory compliance requirement
