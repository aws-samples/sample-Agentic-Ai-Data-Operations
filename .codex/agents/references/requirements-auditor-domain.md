# Requirements Auditor Domain Contract

The Requirements Auditor is the workflow's evidence gate. It compares what the
human said with what the workflow produced. It is not a general reviewer and it
does not make design choices.

## Inputs

- `run/context.json`: authoritative human answers and run progress.
- `run/requirements.jsonl`: append-only user-turn and requirement ledger.
- `run/decisions.jsonl`: append-only agent decisions.
- `logs/trace_events.jsonl`: operational, cognitive, and contextual trace.
- `config/`, `scripts/`, `dags/`, `sql/`, `tests/`, and deployment evidence.

## Required behavior

1. Verify that every `user_turn` record links to explicit requirement IDs.
2. Verify that every authoritative `human_answers` field is represented in the
   ledger.
3. Verify each mandatory requirement's target artifacts exist and satisfy its
   recorded acceptance evidence.
4. Report conflicts and missing evidence as blocking issues.
5. Never infer a primary key, schedule, PII classification, transformation,
   quality threshold, or compliance choice.

The deterministic implementation is
`shared.requirements.auditor.RequirementAuditor`. The agent may explain a
finding, but it must not override the report or silently downgrade a blocker.
