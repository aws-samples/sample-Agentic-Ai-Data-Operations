"""Unit tests for entity_resolved configs, scripts, DAG, and SQL.

Verifies that approved Phase 1 decisions are correctly reflected in artifacts:
  - Source: S3, ad-hoc, no PII, retention=keep_all_versions
  - Silver: PK=entity_id, latest-wins dedup, sedol dropped, aliases->array
  - Quality: silver_threshold>=0.80, critical rules on PK/month-range/country-format
  - DAG: schedule=None (manual), --enable-data-lineage, default_var on Variables
  - SQL: Bronze partitioned by ingestion_date; Silver USING iceberg with array<string> aliases
"""

from pathlib import Path

import pytest
import yaml


WORKLOAD_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"
SCRIPTS_DIR = WORKLOAD_DIR / "scripts"
DAGS_DIR = WORKLOAD_DIR / "dags"
SQL_DIR = WORKLOAD_DIR / "sql"


class TestSourceConfig:
    def test_source_yaml_exists(self):
        assert (CONFIG_DIR / "source.yaml").exists()

    def test_source_type_is_s3(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["source"]["type"] == "s3"

    def test_dedup_key_is_entity_id(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["ingestion"]["dedup_key"] == ["entity_id"]

    def test_manual_schedule(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        # User decision: manual upload, no cron
        assert config["ingestion"]["schedule"] is None
        assert config["source"]["frequency"] == "ad_hoc"

    def test_retention_keeps_all_versions(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["ingestion"]["retention"]["policy"] == "keep_all_versions"
        assert config["ingestion"]["retention"]["s3_versioning"] is True


class TestSemanticConfig:
    def test_semantic_yaml_exists(self):
        assert (CONFIG_DIR / "semantic.yaml").exists()

    def test_no_pii_columns(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        pii_columns = [c for c in config["columns"] if c.get("pii")]
        assert len(pii_columns) == 0, "Public reference data — no PII expected"

    def test_entity_id_is_identifier(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        entity_id = next(c for c in config["columns"] if c["name"] == "entity_id")
        assert entity_id["role"] == "identifier"
        assert "unique" in entity_id["constraints"]
        assert "not_null" in entity_id["constraints"]

    def test_sedol_dropped(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        col_names = [c["name"] for c in config["columns"]]
        assert "sedol" not in col_names
        dropped = [c["name"] for c in config.get("dropped_columns", [])]
        assert "sedol" in dropped

    def test_aliases_is_array(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        aliases = next(c for c in config["columns"] if c["name"] == "aliases")
        assert aliases["semantic_type"] == "array_of_string"

    def test_dimensions_defined(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        dims = [c for c in config["columns"] if c.get("role") == "dimension"]
        # exchange, country, sector, industry
        assert len(dims) >= 4


class TestTransformationConfig:
    def test_transformations_yaml_exists(self):
        assert (CONFIG_DIR / "transformations.yaml").exists()

    def test_dedup_strategy_keep_latest(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        dedup = config["bronze_to_silver"]["deduplication"]
        assert dedup["strategy"] == "keep_latest"
        assert dedup["key"] == ["entity_id"]
        assert dedup["order_by"] == "ingestion_ts"

    def test_sedol_explicitly_dropped(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        dropped = [d["column"] for d in config["bronze_to_silver"]["dropped_columns"]]
        assert "sedol" in dropped

    def test_aliases_split_derived(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        derived = config["bronze_to_silver"]["derived_columns"]
        aliases = next(d for d in derived if d["name"] == "aliases")
        assert "SPLIT" in aliases["expression"].upper()
        assert aliases["replaces_source"] is True

    def test_load_strategy_is_overwrite_iceberg(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        load = config["bronze_to_silver"]["load_strategy"]
        assert load["mode"] == "overwrite"
        assert load["target_format"] == "iceberg"

    def test_no_silver_to_gold_section(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        # Bronze + Silver only per Phase 1 scope
        assert "silver_to_gold" not in config


class TestQualityConfig:
    def test_quality_yaml_exists(self):
        assert (CONFIG_DIR / "quality_rules.yaml").exists()

    def test_silver_threshold(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        assert config["quality"]["silver_threshold"] >= 0.80

    def test_no_gold_threshold(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        # Bronze + Silver only
        assert config["quality"]["gold_threshold"] is None

    def test_critical_rules_on_pk_and_business_rules(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        all_rules = []
        for dim in config["dimensions"].values():
            if isinstance(dim, list):
                all_rules.extend(dim)
        critical = [r for r in all_rules if r.get("severity") == "critical"]
        critical_targets = {
            (r.get("column") or tuple(r.get("columns", [])))
            for r in critical
        }
        # PK uniqueness + completeness on PK; month-range + country-format business rules
        assert "entity_id" in critical_targets
        assert ("entity_id",) in critical_targets or "entity_id" in critical_targets
        assert "fiscal_year_end_month" in critical_targets
        assert "country" in critical_targets

    def test_isin_format_warning(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        isin_rule = next(r for r in validity if r["column"] == "isin")
        assert isin_rule["severity"] == "warning"
        assert "[A-Z0-9]{12}" in isin_rule["rule"]


class TestScripts:
    def test_bronze_script_exists(self):
        assert (SCRIPTS_DIR / "extract" / "ingest_to_bronze.py").exists()

    def test_silver_script_exists(self):
        assert (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").exists()

    def test_quality_script_exists(self):
        assert (SCRIPTS_DIR / "quality" / "run_quality_checks.py").exists()

    def test_silver_script_uses_lineage_routing(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "enable-data-lineage" in script or "lineage" in script

    def test_silver_script_reads_from_catalog(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "from_catalog" in script

    def test_silver_script_writes_iceberg(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "iceberg" in script.lower()

    def test_silver_script_drops_sedol(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert 'drop("sedol")' in script

    def test_silver_script_splits_aliases(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "F.split" in script and "aliases" in script

    def test_silver_script_dedups_by_entity_id(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert 'partitionBy("entity_id")' in script
        assert "row_number" in script

    def test_scripts_use_structured_logger(self):
        for path in [
            SCRIPTS_DIR / "extract" / "ingest_to_bronze.py",
            SCRIPTS_DIR / "transform" / "bronze_to_silver.py",
            SCRIPTS_DIR / "quality" / "run_quality_checks.py",
        ]:
            script = path.read_text()
            assert "StructuredLogger" in script, f"{path.name} missing StructuredLogger"


class TestDAG:
    DAG_FILE = "entity_resolved_pipeline.py"

    def test_dag_file_exists(self):
        assert (DAGS_DIR / self.DAG_FILE).exists()

    def test_dag_has_catchup_false(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert "catchup=False" in dag_code

    def test_dag_has_max_active_runs_1(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert "max_active_runs=1" in dag_code

    def test_dag_has_retries(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert '"retries": 3' in dag_code

    def test_dag_uses_manual_schedule(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert "schedule=None" in dag_code

    def test_dag_has_lineage_flag(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert '"--enable-data-lineage": "true"' in dag_code

    def test_dag_has_on_failure_callback(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert "on_failure_callback" in dag_code

    def test_dag_uses_task_groups(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert "TaskGroup" in dag_code

    def test_dag_uses_variables_with_default_var(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert "Variable.get" in dag_code
        assert "default_var" in dag_code

    def test_dag_passes_run_id_to_scripts(self):
        dag_code = (DAGS_DIR / self.DAG_FILE).read_text()
        assert '"--run_id"' in dag_code


class TestSQL:
    def test_bronze_sql_exists(self):
        assert (SQL_DIR / "bronze" / "create_bronze_table.sql").exists()

    def test_bronze_sql_partitioned_by_ingestion_date(self):
        sql = (SQL_DIR / "bronze" / "create_bronze_table.sql").read_text()
        assert "PARTITIONED BY (ingestion_date" in sql

    def test_silver_sql_uses_iceberg(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        assert "USING iceberg" in sql

    def test_silver_sql_has_aliases_array(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        assert "aliases" in sql and "ARRAY<STRING>" in sql

    def test_silver_sql_no_sedol(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        # Strip SQL comments so the rationale-comment doesn't trip this check.
        non_comment = "\n".join(
            line for line in sql.splitlines() if not line.strip().startswith("--")
        )
        assert "sedol" not in non_comment.lower()

    def test_silver_sql_entity_id_not_null(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        # entity_id must be NOT NULL on the Silver table
        lines = [line.strip() for line in sql.splitlines()]
        entity_id_line = next(line for line in lines if line.startswith("entity_id"))
        assert "NOT NULL" in entity_id_line


class TestToolRoutingDecisions:
    def test_bronze_uses_correct_tool(self):
        script = (SCRIPTS_DIR / "extract" / "ingest_to_bronze.py").read_text()
        assert "s3-copy-sync" in script or "core" in script

    def test_silver_uses_correct_tool(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "glue-etl-iceberg-silver" in script or "glue-athena" in script

    def test_quality_uses_correct_tool(self):
        script = (SCRIPTS_DIR / "quality" / "run_quality_checks.py").read_text()
        assert "glue-data-quality" in script or "glue-athena" in script
