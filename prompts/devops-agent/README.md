# DevOps Agent

**Agent Type**: CI/CD / Operations
**Runs**: Continuous (automated)
**Status**: 🟡 **Partial** — `iac-generator` available; CI/CD, monitoring, cost prompts still planned

## Purpose

The DevOps Agent automates deployment, monitoring, and maintenance of data pipelines. It handles CI/CD, infrastructure as code, observability, and operational tasks.

### Current capability

Today, the agent can generate deployable IaC (Terraform / AWS CDK / CloudFormation) from a completed workload's artifacts. It does NOT apply the IaC — a human reviews and applies manually as a deliberate review step. See [`iac-generator.md`](./iac-generator.md).

## Planned Capabilities

### 🚀 CI/CD Automation

**Deployment Pipelines**:
- Automatically deploy pipeline changes on git push
- Run tests before deployment (unit, integration, quality)
- Blue/green deployments for zero-downtime updates
- Rollback on failures

**Infrastructure as Code**:
- Generate Terraform/CDK for all AWS resources
- Version control for infrastructure changes
- Drift detection (compare actual vs desired state)

**Example Workflow**:
```
Git Push → CI runs tests → Deploy to staging → Smoke tests pass → Deploy to production
```

### 📊 Monitoring & Observability

**Pipeline Monitoring**:
- DAG success/failure alerts (Slack, email, PagerDuty)
- Data quality drift detection (quality scores dropping)
- Pipeline SLA monitoring (runs taking too long)
- Cost anomaly detection (pipeline costs spiking)

**Dashboards**:
- Pipeline health dashboard (success rate, duration, cost)
- Data quality trends (quality scores over time)
- Resource utilization (Glue DPU usage, S3 storage growth)

**Example Alerts**:
```
⚠️ Pipeline 'sales_transactions' failed (Bronze → Silver)
⚠️ Quality score dropped from 0.95 to 0.78
⚠️ Pipeline duration increased 3x (investigate)
```

### 🔧 Operational Tasks

**Automated Maintenance**:
- S3 bucket cleanup (old Bronze/Silver data)
- Glue catalog optimization (compaction, vacuum)
- Lake Formation permission audits
- Cost optimization recommendations

**Self-Healing**:
- Auto-retry failed Glue jobs with backoff
- Scale MWAA workers based on queue depth
- Clean up stuck Athena queries

**Example Actions**:
```
Detected: Bronze data > 90 days old
Action: Archive to S3 Glacier Deep Archive
Savings: $1,200/month
```

### 🤖 Intelligent Operations

**Predictive Maintenance**:
- Predict pipeline failures before they happen
- Recommend infrastructure scaling
- Suggest data retention policies

**Auto-Tuning**:
- Optimize Glue job DPU allocation
- Tune Athena query performance
- Adjust MWAA worker counts

**Cost Optimization**:
- Recommend reserved capacity purchases
- Identify unused resources
- Suggest cheaper storage tiers

## Architecture (Planned)

```
DevOps Agent (Automated, event-driven)
  │
  ├── CI/CD Pipeline
  │   ├── GitHub Actions / AWS CodePipeline
  │   ├── Automated testing (pytest, integration tests)
  │   └── Deployment automation (Terraform/CDK)
  │
  ├── Monitoring Layer
  │   ├── CloudWatch alarms + dashboards
  │   ├── EventBridge rules (pipeline events)
  │   └── SNS notifications (Slack, email)
  │
  ├── Operational Tasks
  │   ├── Lambda functions (scheduled maintenance)
  │   ├── Step Functions (complex workflows)
  │   └── Systems Manager Automation
  │
  └── Intelligence Layer
      ├── SageMaker models (failure prediction)
      ├── Cost Explorer API (optimization)
      └── Bedrock Agent Runtime (decision-making)
```

## Prompts

| Prompt | Purpose | Status |
|--------|---------|--------|
| `iac-generator.md` | Generate Terraform / CDK / CFN for a built workload (manual apply) | ✅ Available |
| `setup-cicd-pipeline.md` | Create CI/CD for workload | 📝 Planned |
| `configure-monitoring.md` | Set up alerts and dashboards | 📝 Planned |
| `automate-maintenance.md` | Schedule operational tasks | 📝 Planned |
| `optimize-costs.md` | Analyze and reduce pipeline costs | 📝 Planned |
| `implement-self-healing.md` | Auto-retry and recovery logic | 📝 Planned |

## Integration Points

**Works with**:
- Data Onboarding Agent (deploys its generated artifacts)
- Ontology Staging Agent (watches for new `ontology.ttl` commits for AWS Semantic Layer sync)
- Environment Setup Agent (manages infrastructure drift)

**Triggered by**:
- Git push (CI/CD)
- CloudWatch alarms (failures, cost spikes)
- Scheduled events (daily maintenance)
- Manual invocation (ad-hoc operations)

## Sample Use Cases

### Use Case 1: Automated Deployment

```
Developer: git push (update transformation logic)
  ↓
DevOps Agent:
  1. Detects change in workloads/sales_transactions/scripts/
  2. Runs unit + integration tests
  3. Deploys to staging MWAA environment
  4. Runs smoke tests (DAG parses, first task succeeds)
  5. Deploys to production MWAA environment
  6. Sends Slack notification: "✅ Deployed sales_transactions v2.3"
```

### Use Case 2: Cost Optimization

```
DevOps Agent (scheduled daily):
  1. Analyzes S3 storage costs
  2. Finds: Bronze data > 90 days (10 TB) = $230/month
  3. Recommends: Move to Glacier Deep Archive = $10/month
  4. Creates PR with Terraform change
  5. Human approves → Agent applies change
  6. Result: $220/month saved
```

### Use Case 3: Pipeline Failure Recovery

```
Pipeline 'customer_master' fails (Bronze → Silver)
  ↓
DevOps Agent:
  1. Detects CloudWatch alarm (Glue job failed)
  2. Checks error: "S3 bucket permission denied"
  3. Attempts auto-fix: Updates Lake Formation grants
  4. Retries Glue job (exponential backoff)
  5. Success → Sends notification: "✅ Auto-recovered"
  6. Failure → Escalates to human: "🚨 Needs investigation"
```

## When Will This Be Available?

**Timeline**: Q2-Q3 2026 (estimated)

**Prerequisites**:
- Data Onboarding Agent fully tested (multiple workloads in production)
- Monitoring patterns identified (common failure modes)
- Cost optimization opportunities documented

**Milestones**:
1. ✅ Data Onboarding Agent (complete)
2. ✅ Ontology Staging Agent (complete — local emission)
3. 🔄 DevOps Agent (design phase)
4. ⏳ CI/CD automation (planned)
5. ⏳ Monitoring & alerting (planned)
6. ⏳ Cost optimization (planned)

## How to Help

Want to accelerate DevOps Agent development?

**Share your needs**:
- What operational tasks take the most time?
- What pipeline failures happen most often?
- What monitoring/alerting do you need?

**Contribute patterns**:
- Common failure recovery scripts
- Cost optimization strategies
- Monitoring dashboard templates

## Temporary Workarounds

Until DevOps Agent is available, use these approaches:

**CI/CD**:
- Manual: Run `workloads/{name}/deploy_to_aws.py` after changes
- GitHub Actions: Create workflow file (see `workloads/financial_portfolios/.github/` example)

**Monitoring**:
- MWAA UI: Check DAG runs manually
- CloudWatch: Set up alarms for Glue job failures
- Cost Explorer: Review costs weekly

**Operational Tasks**:
- S3 lifecycle policies: Manual setup per bucket
- Glue optimization: Run `OPTIMIZE` manually
- Permission audits: Use `cloudtrail` MCP server

## Related Documentation

- `../data-onboarding-agent/README.md` - What DevOps Agent will deploy
- `../environment-setup-agent/README.md` - Initial infrastructure setup
- `../../CLAUDE.md` - Project-level configuration
- `../environment-setup-agent/agentcore/runtime/` - Runtime agent definition (future)

---

**Status**: Placeholder - Coming Q2-Q3 2026

**Questions?** Open an issue: https://github.com/your-org/agentic-data-onboarding/issues
