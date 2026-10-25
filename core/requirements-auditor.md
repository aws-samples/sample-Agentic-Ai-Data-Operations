# Shared Requirements Auditor Contract

The requirements auditor is the final conformance gate for every adapter.
It is deterministic and evidence-driven. It must not infer a business rule
from a column name, an agent prompt, or an observed value.

## Authoritative inputs

Read all of these before deciding:

1. `workloads/{name}/run/context.json`
2. `workloads/{name}/run/requirements.jsonl`
3. `workloads/{name}/run/decisions.jsonl`
4. `workloads/{name}/logs/trace_events.jsonl`
5. workload configs, generated artifacts, tests, and deployment evidence

Every captured user turn must link to one or more explicit requirement
records. Every mandatory requirement must have evidence in a concrete artifact
or an explicit recorded not-applicable decision.

## Execution boundary

- Use `shared.requirements.auditor.audit_workload()`.
- Do not call AWS, MCP, an LLM, or the network.
- Do not modify generated pipeline artifacts.
- Write only the audit report and append-only audit records.

## Required outputs

- `run/requirements_audit.json`
- an appended audit decision in `run/decisions.jsonl`
- an appended `requirements_audit` event in `logs/trace_events.jsonl`

Return success only when the report status is `pass`. Missing, ambiguous,
conflicting, or unsupported mandatory evidence is a blocking failure.
