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
The phase hook denies `Agent` calls until the context and completion marker pass
the same checks as the driver. The requirements auditor hook limits that agent's
writes to its report and append-only audit records.
