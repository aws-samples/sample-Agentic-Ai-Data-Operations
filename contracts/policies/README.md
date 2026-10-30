# ADOP governance policies

`organization/default.yaml` is the shared Bronze, Silver, and Gold baseline.
Optional domain and project files are loaded in this order:

```text
organization → domain → project → per-run override
```

Lower layers may only tighten the inherited policy. Per-run overrides are
stored in `run/context.json#human_answers.contract_overrides` and never modify
the organization default.

Source and target behavior is not stored here. Those are workload-specific
contracts validated by `source_profile.schema.json` and
`target_profile.schema.json`.
