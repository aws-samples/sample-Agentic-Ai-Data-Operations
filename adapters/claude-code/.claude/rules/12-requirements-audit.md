# Requirements capture and conformance

Every human message that supplies onboarding information must be represented
in `workloads/{name}/run/requirements.jsonl`. The `UserPromptSubmit` and
`AskUserQuestion` hooks capture the conversation once the workload run
directory exists. The orchestrator must explicitly classify each captured turn
into requirement records with stable IDs and target artifact paths.

After artifacts and tests exist, run the `requirements-auditor` agent. It must
compare the ledger, human answers, decisions, conversation traces, configs,
generated artifacts, tests, and deployment evidence. A missing or unlinked
conversation event, missing artifact evidence, or conflicting mandatory
requirement blocks promotion.
