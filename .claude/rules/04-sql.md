---
paths:
  - "**/*.sql"
  - "workloads/**/sql/**"
---

# SQL Conventions

- Place SQL files in `workloads/{name}/sql/{zone}/`
- Use fully qualified table names: `database.schema.table`
- Always include `LIMIT` in analytical queries
- Use CTEs over nested subqueries
- Never use `SELECT *` in production queries
- Never include DDL in Gold zone SQL — Gold is read-only for analysis
