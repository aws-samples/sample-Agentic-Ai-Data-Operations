# `/strands-run` — optional AWS Strands runtime

Run the shared headless ADOP orchestration through AWS Strands:

```bash
python3 scripts/run_strands.py status
python3 scripts/run_strands.py run \
  --args <path-to-onboarding-args.json> \
  --region <aws-region> \
  --model <bedrock-model-id>
```

Use `--dry-run` for an offline contract check. AgentCore is optional and is not
required for local or CI execution.
