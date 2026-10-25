---
paths:
  - "**/*.yaml"
  - "**/*.yml"
  - "workloads/**/config/**"
---

# YAML Configuration Conventions

- Use the config schemas from `SKILLS.md` for `source.yaml`, `transformations.yaml`, `quality_rules.yaml`, and `schedule.yaml`
- Never put credentials in YAML — reference Secrets Manager ARNs or Airflow Connection IDs
- Include comments explaining non-obvious configuration choices
