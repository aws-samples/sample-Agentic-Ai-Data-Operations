# Requirements capture and conformance

Every user prompt that supplies onboarding information must be captured in
`workloads/{name}/run/requirements.jsonl`. The `UserPromptSubmit` hook attempts
to capture it automatically. If that hook is unavailable in the running Kiro
surface, the orchestrator must call:

```bash
python3 scripts/capture_user_turn.py \
  --workload "$ADOP_WORKLOAD" \
  --phase "$ADOP_PHASE" \
  --prompt "<exact user message>" \
  --response "<exact agent-facing answer>"
```

Classify each captured turn into explicit requirements with stable IDs and
target artifact paths. After artifacts and tests exist, run the
`requirements-auditor`; any unlinked conversation event, missing artifact
evidence, missing trace lifecycle, or conflicting mandatory requirement blocks
promotion. The auditor write hook permits that agent to write only
`run/requirements_audit.json`, `run/decisions.jsonl`, and
`logs/trace_events.jsonl`.
