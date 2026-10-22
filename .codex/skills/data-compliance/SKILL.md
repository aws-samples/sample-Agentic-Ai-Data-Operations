---
name: data-compliance
description: Inline compliance controls for ADOP data pipelines. Load this whenever
  a pipeline is onboarded with a regulation (GDPR, CCPA, HIPAA, SOX, PCI DSS) so the
  required controls are applied at BUILD time, not as a downstream review. One regulation
  prompt file per framework — legal reviews a prompt file, not application code.
---

# Data Compliance (inline controls)

ADOP applies compliance as an **inline control at onboarding**, not a downstream gate. There is
**one regulation prompt file per governance framework** in `regulations/`. When a workload is
onboarded with a regulation, load that framework's prompt and apply its Silver/Gold rules to the
transformation, quality, and DAG artifacts.

> **Not legal advice.** These prompts encode common control patterns to *support* your compliance
> efforts. You remain responsible for validating that the controls meet your actual regulatory
> obligations. Agents may process regulated/PII data during development — review your data-handling
> practices and access controls before promoting artifacts to production.

## How it plugs into the workflow
1. `/onboard-workflow <REGULATION> ...` sets the active framework.
2. At Phase 3 (profile), tag candidate PII/PHI/PAN columns.
3. At Phase 4 (build), inject the framework's control block into:
   - **Silver** rules — masking/pseudonymization/tokenization of sensitive fields.
   - **Gold** rules — suppression/aggregation-only exposure of sensitive fields.
   - **Quality** rules — validity checks the regulation implies (e.g. Luhn for PCI).
   - **Retention & audit** — retention window + processing-metadata logging.
4. Legal reviews the single prompt file, not the generated PySpark.

## Reasoning effort
`HIPAA | SOX | PCI` are compliance-critical → use `high` reasoning effort for build and review.
`GDPR | CCPA | none` → use `medium` for generation and `low` for deterministic checks. Keep a
high-effort reviewer at the quality chokepoint when the workflow requires one.

## Available frameworks

Read the pack for the active framework in full before generating anything. These are the
control sets themselves, not summaries of them — each is 230-290 lines and names the specific
columns, masking methods, retention windows and audit records the framework requires.

| Token | Pack |
|-------|------|
| GDPR | `runbooks/data-onboarding-agent/regulation/gdpr.md` |
| CCPA | `runbooks/data-onboarding-agent/regulation/ccpa.md` |
| HIPAA | `runbooks/data-onboarding-agent/regulation/hipaa.md` |
| SOX | `runbooks/data-onboarding-agent/regulation/sox.md` |
| PCI / PCI DSS | `runbooks/data-onboarding-agent/regulation/pci-dss.md` |

`runbooks/data-onboarding-agent/regulation/README.md` is the picker: it maps a user's stated
obligation to a token, and states that nothing is applied unless the user selected it.

Paths are relative to the repository root, so the packs and the references in
`.codex/skills/command-onboard-workflow/SKILL.md` resolve consistently in every checkout.

Add a framework by adding a pack in the repository and update the registry and tests that
validate the regulation set.
