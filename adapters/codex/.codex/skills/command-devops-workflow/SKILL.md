---
name: command-devops-workflow
description: "Production readiness for a completed ADOP workload with Codex sub-agents: IaC, monitoring, alerting, cost tags, budget, and runbook. Use when the user invokes $command-devops-workflow or asks to make a built workload production-ready."
---

<!-- Codex-native ADOP workflow skill. The phases use the Codex agent runtime and normal user
     turns; the sub-agent prompts and TBAC human gate are maintained here. -->

# $command-devops-workflow — Production Readiness Workflow

You are the DevOps Agent orchestrating full production readiness for a completed workload with
Codex sub-agents (`spawn_agent` / `wait_agent`). This generates IaC, monitoring, alerting, cost tags, and
an operational runbook — all in parallel.

**PREREQUISITE: The target workload MUST already have a completed pipeline (configs, scripts,
DAG, tests passing). This workflow runs after `$command-onboard-workflow` or manual onboarding
completes.**

---

## Step 1: Parse Arguments

```
$command-devops-workflow
Make customer_master production-ready with Terraform.
```

Arguments:
- Arg 1: workload name (optional — if omitted, list available workloads and ask)
- Arg 2: IaC framework (optional — `terraform` / `cdk` / `cloudformation` — if omitted, ask)

---

## Step 2: Validate Workload Exists

Before any questions, verify:
1. `workloads/{name}/` directory exists
2. `workloads/{name}/config/source.yaml` exists (pipeline was built)
3. `workloads/{name}/scripts/transform/` has rendered scripts
4. `workloads/{name}/dags/` has a DAG file

If ANY check fails:
```
┌────────────────────────────────────────────────────────────────┐
│  ERROR: Workload '{name}' is not ready for DevOps              │
├────────────────────────────────────────────────────────────────┤
│  Missing: {list what's missing}                                │
│  Run $command-onboard-workflow first to build the pipeline.    │
└────────────────────────────────────────────────────────────────┘
```

---

## Step 3: Discovery Questions

Ask these as normal messages to the user, one group at a time, and wait for each answer (in Plan mode, use `request_user_input`):

### Group 1 — IaC Framework
```
[ ] Framework: Terraform / AWS CDK (Python) / AWS CDK (TypeScript) / CloudFormation
[ ] Backend: S3 + DynamoDB (Terraform) / cdk.context.json / S3 (CFN)
[ ] Apply mode: Manual (generate only) / CI/CD (generate + GitHub Actions workflow)
[ ] TBAC principals: which role ARNs get Lake Formation access, and at which
    sensitivity ceiling (NONE / LOW / MEDIUM / HIGH / CRITICAL) per role?
[ ] Query principal: which explicit role ARN will run Athena/query verification?
```

**TBAC principals cannot be derived.** Knowing which columns hold PII tells you what to
protect; it does not tell you who is allowed to read it. You are the only party in this flow
who can ask the user (sub-agents cannot), so ask here — at minimum a Glue service role (typically
`NONE, LOW, MEDIUM`) and one consumer role (typically `NONE, LOW`). If the user declines to
name any, stop: an empty list is a blocking issue, and defaulting to the current IAM caller
would silently grant that caller access to every classification.

Record the answers to Group 1 in `workloads/{name}/run/context.json` under
`human_answers.iac_target_framework` and `human_answers.iac_tbac_principals` (see
`contracts/v1/run_context.schema.json`) so the IaC agent reads what the human actually said
rather than a paraphrase in a prompt string.

Before any IAM, Lake Formation, Glue, or deployment mutation, run
`shared.utils.deployment_guardrails.validate_deployment_preflight`. It must pass
the framework, TBAC, and query-principal checks, require a workload-scoped Glue role, and reject
wildcard IAM actions or an unbounded resource. If it fails, stop before calling
MCP or AWS CLI.

### Group 2 — Monitoring & Alerting
```
[ ] Alert channels: SNS (email) / Slack webhook / PagerDuty / all
[ ] Alert thresholds: defaults (job failure, quality drop, cost spike) or custom
[ ] Dashboard: CloudWatch dashboard for this workload? (yes/no)
```

### Group 3 — Cost & Retention
```
[ ] Cost allocation tags: team, project, environment, workload (confirm tag keys)
[ ] Budget alert threshold (monthly $ limit for this workload's resources)
[ ] Log retention: regulation-driven (auto from compliance config) or custom days
```

### Group 4 — Runbook
```
[ ] On-call team / escalation path (who gets paged?)
[ ] Known failure modes to document (e.g., "S3 permission errors after key rotation")
[ ] Recovery time objective (RTO) — max acceptable downtime
```

---

## Step 4: Reasoning-Effort Routing

| Phase | Source tier | `reasoning_effort` | Reason |
|---|---|---|---|
| Health Check | `low` | Lightweight file verification |
| IaC Generate | `medium` | Code generation (Terraform/CDK) |
| Monitoring | `medium` | CloudWatch + SNS config generation |
| Cost Analysis | `medium` | Resource analysis + tagging |
| Runbook | `medium` | Documentation generation |
| Security Review | `high` | Adversarial IaC review (no IAM wildcards, no public access) |
| Validate | `low` | Syntax checks (terraform validate, cdk synth) |

---

## Step 5: Run the Phases with Codex Sub-Agents

Run the phases below yourself, as the orchestrator, using `spawn_agent`, `wait_agent`, and
`close_agent`. Sub-agents cannot ask the user questions. Every human decision was made in
Step 3, and you pass those answers in.

Before Phase 0, generate `run_id = devops-{workload_name}-{UTC timestamp}`. Record the
start time of each phase for the Step 6 trace log.

### Orchestration rules

- **Parallel** means: spawn every agent in the group, call `wait_agent` with all the
  returned ids, then `close_agent` each one once you have its result.
- **Sequential** means: spawn, wait, and close before the next phase starts.
- Unless a phase names a role, spawn with `agent_type: "default"`. Always pass the prompt
  as `message`.
- Do not set `model`. Sub-agents inherit the session model, which works on every
  provider, including Amazon Bedrock. Use Step 4's tiers as `reasoning_effort`:
  `low`, `medium`, and `high` are Codex reasoning-effort settings. The active model is selected
  by the Codex session or project configuration.
- Placeholders:
  - `{workload_name}` and `{framework}` come from Step 1 or Step 3.
  - `{monitoring}`, `{cost}`, and `{runbook}` are the Step 3 Group 2, 3, and 4 answers,
    serialized as JSON.
  - `{x, default 'y'}` means use the answer `x` if the user gave one, otherwise `y`.
  - `{result, first N characters}` means truncate that earlier result to N characters.
    If the result is missing, write `null`.

### Phase 0: Health Check (sequential, `low`)

```
Verify workload '{workload_name}' is ready for DevOps production readiness.

Check these files exist:
1. workloads/{workload_name}/config/source.yaml
2. workloads/{workload_name}/config/quality.yaml
3. workloads/{workload_name}/scripts/transform/ (has .py files)
4. workloads/{workload_name}/dags/ (has DAG .py file)
5. workloads/{workload_name}/config/schedule.yaml

Also read source.yaml to extract: dataset_name, compliance regulations, PII columns.
Read schedule.yaml to extract: cron, retries, SLA.

Report: READY (with extracted config) or NOT_READY (with missing items).
```

If the result contains `NOT_READY`, stop and report `not_ready` with the result as the
reason.

### Phase 1: IaC + Monitoring + Cost + Runbook (parallel, all `medium`)

**IaC Generator** — spawn with `agent_type: "iac-agent"`. This delegates to the migrated
role rather than restating its rules inline. A second hand-written IaC prompt here would
drift from the role, and the divergent copy is the one that would actually run.

```
You are the IaC Generator for workload: {workload_name}, framework: {framework}.

Your role instructions point to '.codex/agents/references/iac-agent-domain.md'. Read it
in full — it is your prompt, including the hard scope boundary — then
'runbooks/devops-agent/iac-generator.md' for the resource catalog, per-framework file
layout, APPLY_GUIDE.md template and Cedar permit shape.
Follow both. Do not substitute your own plan for theirs.

Inputs: target_framework is '{framework}' (supplied by the human via this command).
Read tbac_principals from workloads/{workload_name}/run/context.json under
human_answers.iac_tbac_principals. If it is missing or empty, stop and return
status "blocked" — do NOT derive grants from the PII columns in source.yaml and do
NOT grant to the current IAM caller.

Write files under workloads/{workload_name}/iac/{framework}/ plus
shared/policies/workloads/{workload_name}/permits.cedar. Generation only — no apply, no
deploy, no AWS calls.

End your final message with a single fenced json block conforming to AgentOutput
(shared/templates/agent_output_schema.py) with a non-empty decisions array; each
entry needs alternatives_considered and rejection_reasons.
```

**Monitoring Agent:**

```
You are the Monitoring Agent for workload: {workload_name}
Alert config: {monitoring}

Generate monitoring resources:

1. CloudWatch Alarms:
   - Glue job failure (any job in this workload)
   - Glue job duration > 2x baseline
   - Quality score drop below threshold
   - S3 storage growth > 20% week-over-week
   - DAG SLA breach

2. SNS Topic + Subscriptions:
   - Topic: {workload_name}-pipeline-alerts
   - Subscriptions based on user config: {monitoring.channels}

3. CloudWatch Dashboard:
   - Pipeline success rate (7-day rolling)
   - Average job duration by stage
   - Data quality score trend
   - Cost per run estimate

4. EventBridge Rules:
   - Glue job state change → SNS
   - MWAA DAG failure → SNS

Return the monitoring configuration (CloudWatch JSON, SNS config, EventBridge rules).
```

**Cost Optimization Agent:**

```
You are the Cost Optimization Agent for workload: {workload_name}
Cost config: {cost}

Generate:

1. Cost Allocation Tags (applied to every resource):
   - workload: {workload_name}
   - team: {cost.team, default 'data-engineering'}
   - environment: {cost.environment, default 'production'}
   - cost_center: {cost.cost_center, default 'data-platform'}
   - compliance: (from source.yaml compliance field)

2. AWS Budget:
   - Monthly budget: ${cost.budget_limit, default 500}
   - Alert at 80% and 100%
   - Notification to SNS topic

3. S3 Lifecycle Policies:
   - Bronze: transition to IA after 30 days, Glacier after 90
   - Silver: retain per compliance (read retention from schedule.yaml)
   - Gold: no lifecycle (hot data)
   - Audit logs: Object Lock + retain per compliance (7 years for SOX/HIPAA)

4. Log Retention:
   - CloudWatch Logs: {cost.log_retention_days, default 90} days
   - Athena query logs: 365 days
   - CloudTrail: regulation-driven

Return the cost configuration (tags map, budget JSON, lifecycle rules).
```

**Runbook Generator** — include the `- Known:` line only if the user named known
failure modes:

```
You are the Runbook Generator for workload: {workload_name}
Runbook config: {runbook}

Generate an operational runbook (Markdown) covering:

1. Pipeline Overview:
   - DAG name, schedule, stages, SLA
   - Data flow diagram (ASCII)

2. Common Failures + Recovery:
   - Glue job OOM → increase DPU
   - S3 permission denied → check LF grants
   - Quality gate failure → check source data, review quarantine
   - DAG timeout → check upstream dependencies
   - Iceberg write conflict → retry with backoff
   - Known: {runbook.known_failures}

3. Escalation Path:
   - L1: Auto-retry (handled by DAG retries)
   - L2: On-call engineer ({runbook.oncall_team, default 'data-engineering'})
   - L3: Team lead (after {runbook.escalation_minutes, default 30} minutes)

4. Rollback Procedures:
   - How to revert a bad Silver/Gold write (Iceberg time-travel)
   - How to replay from Bronze (re-run DAG with backfill)

5. Maintenance Tasks:
   - Weekly: Iceberg compaction (OPTIMIZE)
   - Monthly: Review quality score trends
   - Quarterly: Cost review + right-sizing

6. Contact & Links:
   - On-call: {runbook.oncall_team, default 'data-engineering'}
   - RTO: {runbook.rto_minutes, default 60} minutes
   - Dashboard: CloudWatch link (placeholder)
   - Logs: CloudWatch Log Group link (placeholder)

Return the complete runbook as Markdown.
```

Store the four results as `iac`, `monitoring`, `cost`, and `runbook`.

### Phase 2: Security Review (sequential, `high`)

```
You are a senior cloud security engineer reviewing IaC for workload: {workload_name}

Review the generated IaC for security issues:

CHECK LIST:
1. NO IAM wildcard actions (Action: "*") or wildcard resources (Resource: "*")
2. NO public S3 buckets (Block Public Access must be enabled)
3. NO unencrypted storage (all S3 buckets must have SSE-KMS)
4. NO overly permissive Lake Formation grants (no ALL_DATA_ACCESS)
5. NO hardcoded credentials, account IDs, or secrets
6. Least privilege: each role has only what it needs
7. Encryption in transit: TLS 1.2+ enforced
8. Logging: CloudTrail enabled for all LF operations
9. Tags: all resources tagged (no untagged resources)
10. Network: no public endpoints, VPC-only where applicable

IaC to review:
{iac, first 3000 characters}

Monitoring to review:
{monitoring, first 1000 characters}

Return: { passed: true/false, findings: [{resource, issue, severity, fix}] }
```

Store the result as `security_review`.

### Phase 3: Validate (parallel, both `low`)

IaC syntax:

```
Validate the generated IaC syntax for workload: {workload_name}, framework: {framework}

For Terraform: check HCL syntax is valid, no missing closing braces, variables referenced correctly.
For CDK: check Python/TS syntax, imports are valid, constructs used correctly.
For CloudFormation: check YAML/JSON structure, valid resource types, !Ref targets exist.

IaC content:
{iac, first 2000 characters}

Report: VALID or list syntax errors.
```

Monitoring config:

```
Validate the monitoring configuration for workload: {workload_name}

Check:
- CloudWatch alarm names follow naming convention ({workload_name}-*)
- SNS topic has at least one subscription
- EventBridge rules target valid resources
- Dashboard widget queries are syntactically valid

Monitoring content:
{monitoring, first 1000 characters}

Report: VALID or list issues.
```

Store the results as `validation`, then continue to Step 6 with `status: complete` and
the artifacts `iac`, `monitoring`, `cost`, and `runbook`.

---

## Step 6: After the Phases — Write Files

After Phase 3 finishes, write the actual files:

1. **IaC directory** — `workloads/{name}/iac/{framework}/`
   - `main.tf` / `lib/{name}-stack.ts` / `template.yaml` (depending on framework)
   - `variables.tf` / `bin/app.ts` / `parameters.json`
   - `outputs.tf`
   - `APPLY_GUIDE.md` (manual apply instructions)

2. **Monitoring** — `workloads/{name}/monitoring/`
   - `cloudwatch-alarms.json`
   - `sns-topic.json`
   - `eventbridge-rules.json`
   - `dashboard.json`

3. **Cost config** — `workloads/{name}/config/`
   - Update `schedule.yaml` with retention policies
   - Write `cost_tags.yaml`
   - Write `budget.json`

4. **Runbook** — `workloads/{name}/RUNBOOK.md`

5. **Trace log (MANDATORY)** — `workloads/{name}/logs/trace_events.jsonl`
   - Append DevOps workflow events (don't overwrite existing onboarding trace)

---

## Step 7: Present Summary

```
┌────────────────────────────────────────────────────────────────┐
│  DEVOPS COMPLETE: {workload_name}                              │
├────────────────────────────────────────────────────────────────┤
│  ✓ IaC ({framework})    — workloads/{name}/iac/{framework}/   │
│  ✓ Monitoring           — CloudWatch + SNS + EventBridge       │
│  ✓ Cost Tags + Budget   — $X/month budget, lifecycle policies  │
│  ✓ Runbook              — RUNBOOK.md (failure recovery + SLA)  │
│  ✓ Security Review      — {passed/N issues}                    │
├────────────────────────────────────────────────────────────────┤
│  NEXT STEP: Review APPLY_GUIDE.md, then run:                   │
│    cd workloads/{name}/iac/{framework}/                        │
│    terraform init && terraform plan                             │
└────────────────────────────────────────────────────────────────┘
```

---

## Error Handling

| Situation | Action |
|---|---|
| Workload doesn't exist | Block immediately. Tell user to invoke $command-onboard-workflow first. |
| IaC validation fails | Present errors. Offer auto-fix (re-run IaC agent with error context). |
| Security review finds HIGH issues | Block apply. Present findings. User must acknowledge. |
| Security review finds MEDIUM/LOW | Warn but don't block. Include in APPLY_GUIDE.md. |
| Missing compliance info | Read from workload's source.yaml. If absent, ask user. |
