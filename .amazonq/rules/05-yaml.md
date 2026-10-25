# YAML Configuration Conventions

> **Scope (convention, not runtime-enforced):** these rules apply when writing or
> editing YAML — `**/*.yaml`, `**/*.yml`, and `workloads/**/config/**`. On Claude
> Code this file loaded only for those paths via frontmatter globs; Amazon Q
> Developer CLI has no glob-conditional rule loading, so this rule is always in
> context. Apply it only when the current task touches YAML config, and ignore it
> otherwise.

- Use the config schemas from `SKILLS.md` for `source.yaml`, `transformations.yaml`, `quality_rules.yaml`, and `schedule.yaml`
- Never put credentials in YAML — reference Secrets Manager ARNs or Airflow Connection IDs
- Include comments explaining non-obvious configuration choices
