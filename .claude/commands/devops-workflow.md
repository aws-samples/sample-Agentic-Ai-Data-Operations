---
allowed-tools: Bash(python3:*), Bash(ls:*), Bash(find:*), Bash(grep:*), Bash(aws glue:*), Bash(aws lakeformation:*), Bash(aws s3:ls*), Bash(aws s3:cp*), Bash(aws s3api:head*), Bash(aws s3api:get-object-lock*), Bash(aws cloudwatch:*), Bash(aws sns:*), Bash(aws budgets:*), Bash(aws iam:get-*), Bash(aws iam:list-*), Bash(aws kms:describe*), Bash(aws mwaa:*), Bash(terraform init:*), Bash(terraform fmt:*), Bash(terraform validate:*), Bash(cdk synth:*), Read, Write, Workflow, AskUserQuestion, Agent
description: Production readiness via Dynamic Workflow — IaC, monitoring, alerting, cost analysis, runbook
---

# /devops-workflow — Production Readiness Workflow

You are the DevOps Agent orchestrating full production readiness for a completed workload via
a Claude Code Dynamic Workflow. This generates IaC, monitoring, alerting, cost tags, and
an operational runbook — all in parallel.

**PREREQUISITE: The target workload MUST already have a completed pipeline (configs, scripts,
DAG, tests passing). This command runs AFTER `/onboard-workflow` or manual onboarding completes.**

---

## Step 1: Parse Arguments

```
/devops-workflow                           ← interactive (asks which workload)
/devops-workflow customer_master           ← target specific workload
/devops-workflow customer_master terraform ← workload + IaC framework
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
│  Run /onboard-workflow first to build the pipeline.            │
└────────────────────────────────────────────────────────────────┘
```

---

## Step 3: Discovery Questions

Ask these using `AskUserQuestion`:

### Group 1 — IaC Framework
```
[ ] Framework: Terraform / AWS CDK (Python) / AWS CDK (TypeScript) / CloudFormation
[ ] Backend: S3 + DynamoDB (Terraform) / cdk.context.json / S3 (CFN)
[ ] Apply mode: Manual (generate only) / CI/CD (generate + GitHub Actions workflow)
```

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

## Step 4: Model Routing

| Phase | Model | Reason |
|---|---|---|
| Health Check | haiku | Lightweight file verification |
| IaC Generate | sonnet | Code generation (Terraform/CDK) |
| Monitoring | sonnet | CloudWatch + SNS config generation |
| Cost Analysis | sonnet | Resource analysis + tagging |
| Runbook | sonnet | Documentation generation |
| Security Review | opus | Adversarial IaC review (no IAM wildcards, no public access) |
| Validate | haiku | Syntax checks (terraform validate, cdk synth) |

---

## Step 5: Invoke Dynamic Workflow

```javascript
export const meta = {
  name: 'devops-production-readiness',
  description: 'Generate IaC, monitoring, alerting, cost tags, and runbook for a workload',
  phases: [
    { title: 'Health Check', detail: 'Verify workload artifacts exist' },
    { title: 'IaC Generate', detail: 'Generate Terraform/CDK/CFN for all resources' },
    { title: 'Monitoring', detail: 'CloudWatch dashboards + SNS alerts + EventBridge rules' },
    { title: 'Cost & Tags', detail: 'Cost allocation tags + budget alerts + retention policies' },
    { title: 'Runbook', detail: 'Auto-generated operational runbook' },
    { title: 'Security Review', detail: 'Adversarial review of all generated IaC' },
    { title: 'Validate', detail: 'Syntax validation (terraform fmt, cdk synth, cfn-lint)' }
  ]
}

const WL_NAME = args.workload_name
const FRAMEWORK = args.framework
const MONITORING = args.monitoring
const COST = args.cost
const RUNBOOK = args.runbook

// ─── Phase 0: Health Check ─────────────────────────────────────────
phase('Health Check')
const health = await agent(
  `Verify workload '${WL_NAME}' is ready for DevOps production readiness.\n\n` +
  `Check these files exist:\n` +
  `1. workloads/${WL_NAME}/config/source.yaml\n` +
  `2. workloads/${WL_NAME}/config/quality.yaml\n` +
  `3. workloads/${WL_NAME}/scripts/transform/ (has .py files)\n` +
  `4. workloads/${WL_NAME}/dags/ (has DAG .py file)\n` +
  `5. workloads/${WL_NAME}/config/schedule.yaml\n\n` +
  `Also read source.yaml to extract: dataset_name, compliance regulations, PII columns.\n` +
  `Read schedule.yaml to extract: cron, retries, SLA.\n\n` +
  `Report: READY (with extracted config) or NOT_READY (with missing items).`,
  { model: 'haiku', label: `health:${WL_NAME}`, phase: 'Health Check' }
)
log(`Health: ${health ? health.substring(0, 80) : 'null'}`)

if (health && health.includes('NOT_READY')) {
  return { status: 'not_ready', workload: WL_NAME, reason: health }
}

// ─── Phase 1: IaC + Monitoring + Cost + Runbook (parallel) ─────────
phase('IaC Generate')
const buildResults = await parallel([
  // IaC Generator
  () => agent(
    `You are the IaC Generator for workload: ${WL_NAME}\n` +
    `Framework: ${FRAMEWORK}\n\n` +
    `Read the workload config from workloads/${WL_NAME}/config/ and generate IaC for:\n\n` +
    `AWS Resources to codify:\n` +
    `1. S3 bucket (or reference existing) with lifecycle policies\n` +
    `2. Glue Database + Tables (Bronze, Silver, Gold)\n` +
    `3. Glue Jobs (one per transform script in scripts/transform/)\n` +
    `4. Glue Data Quality Rulesets\n` +
    `5. Lake Formation LF-Tags + TBAC grants (based on PII columns in source.yaml)\n` +
    `6. KMS key (if compliance requires encryption)\n` +
    `7. IAM roles (Glue execution role, LF admin, data steward, analyst)\n` +
    `8. MWAA DAG deployment (S3 sync)\n\n` +
    `Generate the IaC in ${FRAMEWORK} format. Include:\n` +
    `- Variables/parameters for account_id, region, environment\n` +
    `- No hardcoded values — all configurable\n` +
    `- Tagging on every resource (workload, team, environment, cost_center)\n` +
    `- Output values (table ARNs, role ARNs, bucket paths)\n\n` +
    `Return the complete IaC code.`,
    { model: 'sonnet', label: `iac:${WL_NAME}`, phase: 'IaC Generate' }
  ),

  // Monitoring Setup
  () => agent(
    `You are the Monitoring Agent for workload: ${WL_NAME}\n` +
    `Alert config: ${JSON.stringify(MONITORING)}\n\n` +
    `Generate monitoring resources:\n\n` +
    `1. CloudWatch Alarms:\n` +
    `   - Glue job failure (any job in this workload)\n` +
    `   - Glue job duration > 2x baseline\n` +
    `   - Quality score drop below threshold\n` +
    `   - S3 storage growth > 20% week-over-week\n` +
    `   - DAG SLA breach\n\n` +
    `2. SNS Topic + Subscriptions:\n` +
    `   - Topic: ${WL_NAME}-pipeline-alerts\n` +
    `   - Subscriptions based on user config: ${JSON.stringify(MONITORING.channels)}\n\n` +
    `3. CloudWatch Dashboard:\n` +
    `   - Pipeline success rate (7-day rolling)\n` +
    `   - Average job duration by stage\n` +
    `   - Data quality score trend\n` +
    `   - Cost per run estimate\n\n` +
    `4. EventBridge Rules:\n` +
    `   - Glue job state change → SNS\n` +
    `   - MWAA DAG failure → SNS\n\n` +
    `Return the monitoring configuration (CloudWatch JSON, SNS config, EventBridge rules).`,
    { model: 'sonnet', label: `monitoring:${WL_NAME}`, phase: 'Monitoring' }
  ),

  // Cost & Tags
  () => agent(
    `You are the Cost Optimization Agent for workload: ${WL_NAME}\n` +
    `Cost config: ${JSON.stringify(COST)}\n\n` +
    `Generate:\n\n` +
    `1. Cost Allocation Tags (applied to every resource):\n` +
    `   - workload: ${WL_NAME}\n` +
    `   - team: ${COST.team || 'data-engineering'}\n` +
    `   - environment: ${COST.environment || 'production'}\n` +
    `   - cost_center: ${COST.cost_center || 'data-platform'}\n` +
    `   - compliance: (from source.yaml compliance field)\n\n` +
    `2. AWS Budget:\n` +
    `   - Monthly budget: $${COST.budget_limit || 500}\n` +
    `   - Alert at 80% and 100%\n` +
    `   - Notification to SNS topic\n\n` +
    `3. S3 Lifecycle Policies:\n` +
    `   - Bronze: transition to IA after 30 days, Glacier after 90\n` +
    `   - Silver: retain per compliance (read retention from schedule.yaml)\n` +
    `   - Gold: no lifecycle (hot data)\n` +
    `   - Audit logs: Object Lock + retain per compliance (7 years for SOX/HIPAA)\n\n` +
    `4. Log Retention:\n` +
    `   - CloudWatch Logs: ${COST.log_retention_days || 90} days\n` +
    `   - Athena query logs: 365 days\n` +
    `   - CloudTrail: regulation-driven\n\n` +
    `Return the cost configuration (tags map, budget JSON, lifecycle rules).`,
    { model: 'sonnet', label: `cost:${WL_NAME}`, phase: 'Cost & Tags' }
  ),

  // Runbook
  () => agent(
    `You are the Runbook Generator for workload: ${WL_NAME}\n` +
    `Runbook config: ${JSON.stringify(RUNBOOK)}\n\n` +
    `Generate an operational runbook (Markdown) covering:\n\n` +
    `1. Pipeline Overview:\n` +
    `   - DAG name, schedule, stages, SLA\n` +
    `   - Data flow diagram (ASCII)\n\n` +
    `2. Common Failures + Recovery:\n` +
    `   - Glue job OOM → increase DPU\n` +
    `   - S3 permission denied → check LF grants\n` +
    `   - Quality gate failure → check source data, review quarantine\n` +
    `   - DAG timeout → check upstream dependencies\n` +
    `   - Iceberg write conflict → retry with backoff\n` +
    `   ${RUNBOOK.known_failures ? '- Known: ' + JSON.stringify(RUNBOOK.known_failures) : ''}\n\n` +
    `3. Escalation Path:\n` +
    `   - L1: Auto-retry (handled by DAG retries)\n` +
    `   - L2: On-call engineer (${RUNBOOK.oncall_team || 'data-engineering'})\n` +
    `   - L3: Team lead (after ${RUNBOOK.escalation_minutes || 30} minutes)\n\n` +
    `4. Rollback Procedures:\n` +
    `   - How to revert a bad Silver/Gold write (Iceberg time-travel)\n` +
    `   - How to replay from Bronze (re-run DAG with backfill)\n\n` +
    `5. Maintenance Tasks:\n` +
    `   - Weekly: Iceberg compaction (OPTIMIZE)\n` +
    `   - Monthly: Review quality score trends\n` +
    `   - Quarterly: Cost review + right-sizing\n\n` +
    `6. Contact & Links:\n` +
    `   - On-call: ${RUNBOOK.oncall_team || 'data-engineering'}\n` +
    `   - RTO: ${RUNBOOK.rto_minutes || 60} minutes\n` +
    `   - Dashboard: CloudWatch link (placeholder)\n` +
    `   - Logs: CloudWatch Log Group link (placeholder)\n\n` +
    `Return the complete runbook as Markdown.`,
    { model: 'sonnet', label: `runbook:${WL_NAME}`, phase: 'Runbook' }
  )
])
log('IaC + Monitoring + Cost + Runbook generation complete')

// ─── Phase 2: Security Review (Opus) ───────────────────────────────
phase('Security Review')
const secReview = await agent(
  `You are a senior cloud security engineer reviewing IaC for workload: ${WL_NAME}\n\n` +
  `Review the generated IaC for security issues:\n\n` +
  `CHECK LIST:\n` +
  `1. NO IAM wildcard actions (Action: "*") or wildcard resources (Resource: "*")\n` +
  `2. NO public S3 buckets (Block Public Access must be enabled)\n` +
  `3. NO unencrypted storage (all S3 buckets must have SSE-KMS)\n` +
  `4. NO overly permissive Lake Formation grants (no ALL_DATA_ACCESS)\n` +
  `5. NO hardcoded credentials, account IDs, or secrets\n` +
  `6. Least privilege: each role has only what it needs\n` +
  `7. Encryption in transit: TLS 1.2+ enforced\n` +
  `8. Logging: CloudTrail enabled for all LF operations\n` +
  `9. Tags: all resources tagged (no untagged resources)\n` +
  `10. Network: no public endpoints, VPC-only where applicable\n\n` +
  `IaC to review:\n${buildResults[0] ? buildResults[0].substring(0, 3000) : 'null'}\n\n` +
  `Monitoring to review:\n${buildResults[1] ? buildResults[1].substring(0, 1000) : 'null'}\n\n` +
  `Return: { passed: true/false, findings: [{resource, issue, severity, fix}] }`,
  { model: 'opus', label: `security:${WL_NAME}`, phase: 'Security Review' }
)
log(`Security review: ${secReview ? secReview.substring(0, 80) : 'null'}`)

// ─── Phase 3: Validate ─────────────────────────────────────────────
phase('Validate')
const validation = await parallel([
  () => agent(
    `Validate the generated IaC syntax for workload: ${WL_NAME}, framework: ${FRAMEWORK}\n\n` +
    `For Terraform: check HCL syntax is valid, no missing closing braces, variables referenced correctly.\n` +
    `For CDK: check Python/TS syntax, imports are valid, constructs used correctly.\n` +
    `For CloudFormation: check YAML/JSON structure, valid resource types, !Ref targets exist.\n\n` +
    `IaC content:\n${buildResults[0] ? buildResults[0].substring(0, 2000) : 'null'}\n\n` +
    `Report: VALID or list syntax errors.`,
    { model: 'haiku', label: `validate-iac:${WL_NAME}`, phase: 'Validate' }
  ),
  () => agent(
    `Validate the monitoring configuration for workload: ${WL_NAME}\n\n` +
    `Check:\n` +
    `- CloudWatch alarm names follow naming convention (${WL_NAME}-*)\n` +
    `- SNS topic has at least one subscription\n` +
    `- EventBridge rules target valid resources\n` +
    `- Dashboard widget queries are syntactically valid\n\n` +
    `Monitoring content:\n${buildResults[1] ? buildResults[1].substring(0, 1000) : 'null'}\n\n` +
    `Report: VALID or list issues.`,
    { model: 'haiku', label: `validate-monitoring:${WL_NAME}`, phase: 'Validate' }
  )
])
log('Validation complete')

return {
  status: 'complete',
  workload: WL_NAME,
  framework: FRAMEWORK,
  artifacts: {
    iac: buildResults[0],
    monitoring: buildResults[1],
    cost: buildResults[2],
    runbook: buildResults[3]
  },
  security_review: secReview,
  validation
}
```

---

## Step 6: Post-Workflow — Write Files

After the workflow returns, write the actual files:

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
| Workload doesn't exist | Block immediately. Tell user to run /onboard-workflow first. |
| IaC validation fails | Present errors. Offer auto-fix (re-run IaC agent with error context). |
| Security review finds HIGH issues | Block apply. Present findings. User must acknowledge. |
| Security review finds MEDIUM/LOW | Warn but don't block. Include in APPLY_GUIDE.md. |
| Missing compliance info | Read from workload's source.yaml. If absent, ask user. |
