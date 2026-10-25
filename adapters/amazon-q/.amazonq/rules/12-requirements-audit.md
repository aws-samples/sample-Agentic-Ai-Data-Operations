# Requirements capture and conformance

Amazon Q has no reliable structured question tool hook for ordinary free-text
conversation. The orchestrator MUST therefore record every user prompt and
answer after the workload run directory exists:

```bash
python3 scripts/capture_user_turn.py \
  --workload "$ADOP_WORKLOAD" \
  --phase "$ADOP_PHASE" \
  --prompt "<exact user message>" \
  --response "<exact agent-facing answer>"
```

Do this before continuing the workflow. Then classify the turn into explicit
requirements with stable IDs and target artifact paths. After artifacts and
tests exist, run `adop-requirements-auditor`; only a passing audit may promote
or deploy the workload.
