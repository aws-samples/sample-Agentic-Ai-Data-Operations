# Kiro ADOP workflow driver

Kiro's main conversation is the human-facing orchestrator. The filesystem driver
keeps the run state deterministic and makes the discovery gate enforceable:

```text
python3 scripts/kiro_workflow.py init --workload <name>
    ↓
ask the complete Phase 1 questions and capture every Q&A turn
    ↓
write run/context.json and run/discovery_complete.json
    ↓
python3 scripts/kiro_workflow.py gate --workload <name>
    ↓
spawn Kiro sub-agents and run their test gates
    ↓
.kiro/adop/render.sh --workload ... --template ... --out ...
    ↓
python3 scripts/kiro_workflow.py audit --workload <name>
```

The driver never guesses a business answer, creates pipeline code, or calls AWS.
`context.json` is authoritative and must contain the human's verbatim answers.
The phase hook denies `subagent` calls until the context and completion marker
pass the same checks as the driver — `phase_gate.py` and `kiro_workflow.py gate`
share one rule set and must stay in agreement. The requirements auditor's writes
are limited to its report and append-only audit records by the `permissions.rules`
block in its agent definition.

There is no `.kiro/workflows/` definition for this flow and none is needed: the
driver above *is* the workflow, and keeping it a script is what makes the gate
reproducible outside a chat session (CI can run `gate` and `audit` directly).
