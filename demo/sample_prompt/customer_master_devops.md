# Customer Master DevOps Workflow

## Prompt to paste

```
/devops-workflow customer_master terraform
```

This triggers the DevOps Workflow for the `customer_master` workload using Terraform as the IaC framework.

The agent will ask about:
- Alert channels (SNS email, Slack, PagerDuty)
- Budget threshold (monthly $ limit)
- On-call team and escalation path
- Known failure modes to document in the runbook

---

## What gets generated

```
workloads/customer_master/
├── iac/terraform/
│   ├── main.tf               (Glue jobs, S3, KMS, IAM, LF-Tags)
│   ├── variables.tf          (account_id, region, environment)
│   ├── outputs.tf            (ARNs, bucket paths)
│   └── APPLY_GUIDE.md        (step-by-step manual apply instructions)
├── monitoring/
│   ├── cloudwatch-alarms.json (job failure, quality drop, cost spike)
│   ├── sns-topic.json         (alert subscriptions)
│   ├── eventbridge-rules.json (Glue state change → SNS)
│   └── dashboard.json         (pipeline health dashboard)
├── config/
│   ├── cost_tags.yaml         (workload, team, environment, compliance)
│   └── budget.json            (monthly limit + 80%/100% alerts)
└── RUNBOOK.md                 (failure recovery, escalation, maintenance)
```

---

## Prerequisites

- Workload must be fully built (configs + scripts + DAG + tests passing)
- AWS credentials active
- MCP servers healthy (glue-athena, lakeformation required)

---

## Comparison: with vs without workflow

| Aspect | Manual (paste iac-generator.md) | /devops-workflow |
|--------|----------------------------------|------------------|
| IaC | ✓ Generated | ✓ Generated |
| Monitoring | ✗ Manual CloudWatch setup | ✓ Auto-generated |
| Cost tags | ✗ Manual | ✓ Auto-generated + budget |
| Runbook | ✗ Manual | ✓ Auto-generated |
| Security review | ✗ Manual | ✓ Opus adversarial review |
| Time | ~20 min (IaC only) | ~10 min (all parallel) |
