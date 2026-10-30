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
    ↓
Phase 5 Deploy (main conversation, MCP — MCP_GUARDRAILS.md Phase 5):
  kiro_workflow.py deploy-check --workload <name> preflight --glue-role <workload>-glue-service-role
  S3 upload, Glue catalog, IAM (MCP)
  kiro_workflow.py deploy-check --workload <name> simulate --region <r> \
      --mwaa-role-arn <arn> --glue-role-arn <arn> --jobs <jobs...> --databases <dbs...> --kms-key-arn <arn>
  Lake Formation, KMS, query verify, audit trail (MCP)
  Glue jobs (create_job/update_job) + MWAA DAG upload (MCP / CLI)
  kiro_workflow.py verify --workload <name> --database <db> --tables <t...> --query-principal-arn <arn> \
      --mwaa-env <env> --dag-id <id> --mwaa-role-arn <arn> --glue-role-arn <arn> --glue-jobs <jobs...> --kms-key-arn <arn>
    ↓
before ANY manual Glue job start (E2E, re-run, backfill):
  kiro_workflow.py deploy-check --workload <name> active-runs --region <r> --jobs <jobs...>
    ↓
Step 5.10 E2E offer → Step 5.11 DevOps offer
```

Every `deploy-check`/`verify` exits 2 on failure: stop, show the JSON, fix, re-run. Never
skip one. `simulate` covers the MWAA role's `glue:GetJob`/`StartJobRun`/`GetJobRun` and
`iam:PassRole` on the Glue role, plus the Glue role's catalog (including `default`) and KMS
calls. `verify` is Step 5.9; its MWAA check fails on any `dags list-import-errors` entry.
`preflight` and `simulate` refuse to run until `run/requirements_audit.json` has
`status: pass` for the current `run_id` and is newer than `context.json` and everything
under `config/`, `scripts/`, `dags/` and `sql/`. A passing `preflight` writes
`run/deploy_gate.json`, and the `adop-deploy-gate` PreToolUse hook denies every deploy
mutation until that file exists — so the audit cannot be bypassed by calling an AWS tool
directly instead of going through the driver. Never hand-write `deploy_gate.json`.
These are the same `shared.utils.deployment_checks` gates Claude Code and Codex run.

The driver never guesses a business answer, creates pipeline code, or mutates AWS;
its only AWS calls are the read-only Phase 5 checks (IAM simulation, Glue job-run
listing, Step 5.9 verification).
`context.json` is authoritative and must contain the human's verbatim answers.
The phase hook denies `subagent` calls until the context and completion marker
pass the same checks as the driver — `phase_gate.py` and `kiro_workflow.py gate`
share one rule set and must stay in agreement. The requirements auditor's writes
are limited to its report and append-only audit records by the `permissions.rules`
block in its agent definition.

There is no `.kiro/workflows/` definition for this flow and none is needed: the
driver above *is* the workflow, and keeping it a script is what makes the gate
reproducible outside a chat session (CI can run `gate` and `audit` directly).
