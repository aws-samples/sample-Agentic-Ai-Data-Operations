# SQL Conventions

> **Scope (convention, not runtime-enforced):** these rules apply when writing or
> editing SQL — `**/*.sql` and `workloads/**/sql/**`. On Claude Code this file
> loaded only for those paths via frontmatter globs; Amazon Q Developer CLI has no
> glob-conditional rule loading, so this rule is always in context. Apply it only
> when the current task touches SQL, and ignore it otherwise.

- Place SQL files in `workloads/{name}/sql/{zone}/`
- Use fully qualified table names: `database.schema.table`
- Always include `LIMIT` in analytical queries
- Use CTEs over nested subqueries
- Never use `SELECT *` in production queries
- Never include DDL in Gold zone SQL — Gold is read-only for analysis
