# ADOP cost attribution

ADOP records Bedrock and AgentCore usage at three levels:

| Level | Source of truth | Visible dimensions |
|---|---|---|
| Project billing | Bedrock Application Inference Profile tags and AWS CUR | project, environment, cost center, owner |
| Workload/run evidence | `workloads/{name}/run/cost_events.jsonl` | project, workload, run, phase |
| Agent usage | `trace_events.jsonl` and cost events | agent, model, inference profile, token counts |

AWS billing remains authoritative for dollars. ADOP records token usage and
the dimensions needed to reconcile billed totals; it does not hardcode model
prices.

## Human discovery

Every new onboarding run must capture these values explicitly:

- project
- environment
- cost center
- owner/team
- existing Bedrock Application Inference Profile, or approval to provision one

The answers are stored under `human_answers.cost_attribution` in
`run/context.json`. The workload-level deployment contract is stored in
`config/cost_attribution.yaml`.

Do not infer billing dimensions from the workload name, Git branch, AWS caller,
or source path.

## Workload contract

```yaml
schema_version: v1
project: customer_orders
environment: production
cost_center: data-platform
owner: analytics

# Use one profile for the project, or separate profiles when CUR-level
# chargeback must distinguish agents.
bedrock_inference_profile_arn: ${ADOP_BEDROCK_PROFILE_ARN}
agent_inference_profiles:
  orchestrator: ${ADOP_BEDROCK_ORCHESTRATOR_PROFILE_ARN}
  metadata: ${ADOP_BEDROCK_METADATA_PROFILE_ARN}
  transformation: ${ADOP_BEDROCK_TRANSFORMATION_PROFILE_ARN}
  quality: ${ADOP_BEDROCK_QUALITY_PROFILE_ARN}
  dag: ${ADOP_BEDROCK_DAG_PROFILE_ARN}
```

The schema is `contracts/v1/cost_attribution.schema.json`. Profile ARNs may be
environment references; secrets must never be placed in this file.

## Reporting

After a runtime has emitted usage events, show project/workload/agent usage with:

```bash
python3 -m shared.utils.cost_attribution summary
python3 -m shared.utils.cost_attribution summary --workload customer_orders
python3 -m shared.utils.cost_attribution summary --workload customer_orders --json
```

The report includes input tokens, output tokens, total tokens, inference
profiles, and optional estimates. Reconcile official dollar amounts from AWS
Cost Explorer or CUR.
