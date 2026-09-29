# Runbooks

Human-invoked playbooks, organized by the agent persona that owns them. You open a runbook and
follow it, or the orchestrator reads one on demand.

## Runbooks vs `.claude/agents/` — which is which

This folder was called `prompts/`, and that name caused real confusion, because
`.claude/agents/` also holds prompts. They are different things:

| | `runbooks/` (this folder) | `.claude/agents/` |
|---|---|---|
| Loaded by | a human, or the orchestrator via `Read` | Claude Code, automatically on spawn |
| Discovered by the harness? | **No** — nothing parses these files | **Yes** — `subagent_type: "quality-agent"` resolves here |
| `tools:` frontmatter enforced? | No, there is none | **Yes**, it is an allowlist |
| Path matters? | No, only the links pointing at it | **Yes** — must be exactly `.claude/agents/{name}.md` |
| Typical size | 3–45 KB procedures | ~90 lines, scoped |
| Change takes effect | next time someone reads it | within seconds (file-watched) |

**Rule of thumb**: to change how a pipeline sub-agent behaves, edit `.claude/agents/`. To change
an operator procedure — AWS setup, compliance controls, troubleshooting, IaC — edit a runbook.

Two files here blur the line and are worth calling out. Both follow the same split — short
enforced prompt in `.claude/agents/`, long reference narrative here:

- `data-onboarding-agent/ontology-staging-agent.md` → live prompt is
  `.claude/agents/ontology-agent.md`.
- `devops-agent/iac-generator.md` → live prompt is `.claude/agents/iac-agent.md`. The runbook
  keeps the resource catalog, per-framework file layouts and validator matrix that would bloat
  every spawn; the agent reads it on demand. Two of its instructions are superseded and
  labelled as such in place: "ask the user" (sub-agents have no `AskUserQuestion`) and
  `submit_agent_output` (a Bedrock-only tool spec).

Anything spawned as a sub-agent — registered or inline — must return an `AgentOutput` whose
`decisions` array has at least one entry. That is enforced in
`shared/templates/agent_output_schema.py`, so an empty array fails the same as omitting it. See
`.claude/rules/07-error-logging.md`.

## Quick navigation

| Persona | Folder | When to use | Status |
|---|---|---|---|
| **Environment Setup** | [`environment-setup-agent/`](environment-setup-agent/) | First time in an AWS account | Ready |
| **Data Onboarding** | [`data-onboarding-agent/`](data-onboarding-agent/) | Per data source (repeatable) | Ready |
| **Regulation library** | [`data-onboarding-agent/regulation/`](data-onboarding-agent/regulation/) | Only when a regulation is selected | Ready |
| **Troubleshooting** | [`data-onboarding-agent/troubleshooting/`](data-onboarding-agent/troubleshooting/) | Iceberg/Glue errors, trace debugging | Ready |
| **DevOps** | [`devops-agent/`](devops-agent/) | IaC generation today; CI/CD + monitoring planned | Partial |
| **Examples & helpers** | [`examples/`](examples/) | Synthetic data for demos and testing | Ready |

## Typical journey

### First-time setup (once per AWS account)

```
environment-setup-agent/
├── 01-setup-aws-infrastructure.md    (20 min)
├── 02-deploy-agentcore-gateway.md    (15 min — optional, Gateway mode)
└── 03-deploy-agentcore-runtime.md    (10 min — optional)
```

Result: IAM roles, S3 zone buckets, KMS keys, Glue databases, LF-Tags, MWAA.

### Onboarding a data source (per source)

```
data-onboarding-agent/
├── 01-route-check-existing.md        (< 1 min — is it already onboarded?)
├── 03-onboard-build-pipeline.md      (45 min — master runbook, phases 0-5)
├── 04-enrich-link-datasets.md        (5 min — optional)
└── 05-govern-trace-lineage.md        (5 min — optional)

examples/
└── generate-synthetic-data.md        (2-5 min — demo/test data)
```

Result: `workloads/{name}/` with pipeline, DAG and tests, deployed to AWS.

The slash command `/onboard-workflow [REGULATION...]` runs this end to end and is usually the
better entry point; the runbook is what it follows.

### Operating what you built

```
devops-agent/
└── iac-generator.md                  (Terraform / CDK / CloudFormation from a built workload)

data-onboarding-agent/troubleshooting/
├── 01-fix-iceberg-glue.md
└── 02-deep-agent-logging.md
```

## Regulation library

Not applied by default. The orchestrator loads exactly one file per selected regulation during
Phase 1 discovery — see the dispatch list in `SKILLS.md`.

| File | Regulation | Key focus |
|---|---|---|
| [gdpr.md](data-onboarding-agent/regulation/gdpr.md) | GDPR | Right to erasure, consent, minimization, 365-day retention |
| [ccpa.md](data-onboarding-agent/regulation/ccpa.md) | CCPA | Right to know/delete, opt-out tracking, lineage |
| [hipaa.md](data-onboarding-agent/regulation/hipaa.md) | HIPAA | PHI protection, BAA, minimum necessary, KMS |
| [sox.md](data-onboarding-agent/regulation/sox.md) | SOX | Financial integrity, 0.95+ quality gate, 7-year audit |
| [pci-dss.md](data-onboarding-agent/regulation/pci-dss.md) | PCI DSS | Cardholder masking, restricted access, Luhn validation |

Adding one touches four places: the file here, the dispatch list in `SKILLS.md`, the table
above, and the `compliance_rules.regulation` enum in
`contracts/v1/quality_spec.schema.json`. Mind the spellings — the enum says `PCI_DSS`, the file
is `pci-dss.md`, and the slash command takes `PCI DSS`.

## Related documentation

| File | Purpose |
|---|---|
| [`../CLAUDE.md`](../CLAUDE.md) | Project rules, human-in-the-loop gate |
| [`../SKILLS.md`](../SKILLS.md) | Orchestrator + sub-agent skill definitions |
| [`../MCP_GUARDRAILS.md`](../MCP_GUARDRAILS.md) | Per-phase MCP tool guardrails |
| [`../TOOL_ROUTING.md`](../TOOL_ROUTING.md) | Which MCP tool for which task |
| [`../docs/workflow-diagrams.md`](../docs/workflow-diagrams.md) | Visual workflow diagrams |
| [`../docs/getting-started.md`](../docs/getting-started.md) | New-builder walkthrough |

---

**Start here**: [`environment-setup-agent/01-setup-aws-infrastructure.md`](environment-setup-agent/01-setup-aws-infrastructure.md)
(first time only), then
[`data-onboarding-agent/01-route-check-existing.md`](data-onboarding-agent/01-route-check-existing.md)
per data source.
