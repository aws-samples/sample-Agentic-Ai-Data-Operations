# Python & Airflow Conventions

> **Scope (convention, not runtime-enforced):** these rules apply when writing or
> editing Python files — `workloads/**/*.py`, `shared/**/*.py`, `dags/**/*.py`,
> `scripts/**/*.py`. On Claude Code this file loaded only for those paths via
> frontmatter globs; Amazon Q Developer CLI has no glob-conditional rule loading,
> so this rule is always in context. Apply it only when the current task touches
> Python/Airflow code, and ignore it otherwise.

## Python (DAGs & Scripts)

- Follow the DAG template in `SKILLS.md` (Orchestration DAG Agent section)
- Use Airflow Variables and Connections for all configuration — zero hardcoded values
- Use `TaskGroup` (not `SubDagOperator`)
- Use `PythonOperator` calling scripts in `workloads/{name}/scripts/`, not inline logic
- Set `catchup=False`, `max_active_runs=1`, `retries=3` with exponential backoff as defaults
- Every DAG must have `on_failure_callback`, `sla` on critical tasks, and `doc_md`

## Airflow DAG Rules

**Always**: `catchup=False`, `max_active_runs=1`, `retries=3`, exponential backoff, `on_failure_callback`, `TaskGroup` for stage organization, Airflow Variables for config.

**Never**: Hardcoded secrets, `SubDagOperator`, `provide_context=True`, `start_date=datetime.now()`, `depends_on_past=True` (without justification), inline computation in DAG files, disabled retries in production.

## All Variable.get() calls MUST have `default_var`

Without `default_var`, DAG fails to parse and won't appear in Airflow UI.

```python
# CORRECT
glue_role = Variable.get("glue_iam_role", default_var="AWSGlueServiceRole")

# WRONG — breaks DAG parsing
glue_role = Variable.get("glue_iam_role")
```

## Glue ETL Scripts

- All ETL scripts MUST target AWS Glue ETL (PySpark + GlueContext + Iceberg)
- Iceberg write: `.saveAsTable("glue_catalog.db.table")`
- Iceberg read: `spark.table("glue_catalog.db.table")`
- Lineage writes: use boto3 S3 client, NOT `saveAsTextFile()`
