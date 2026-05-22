"""Unit tests for estimates_eps configs, scripts, DAG, and SQL."""

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

    def test_dedup_key(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["ingestion"]["dedup_key"] == ["entity_id", "estimate_date", "period_type"]

    def test_manual_schedule(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["ingestion"]["schedule"] is None
        assert config["source"]["frequency"] == "ad_hoc"


class TestSemanticConfig:
    def test_no_pii_columns(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        assert all(not c.get("pii") for c in config["columns"])

    def test_measures_present(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        measures = [c["name"] for c in config["columns"] if c.get("role") == "measure"]
        for m in ("eps_mean", "eps_high", "eps_low", "num_analysts"):
            assert m in measures

    def test_entity_id_has_fk(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        entity_id = next(c for c in config["columns"] if c["name"] == "entity_id")
        assert entity_id.get("relationship", {}).get("target_table") == "silver_entity_resolved"


class TestTransformationConfig:
    def test_dedup_keep_latest(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        dedup = config["bronze_to_silver"]["deduplication"]
        assert dedup["strategy"] == "keep_latest"
        assert dedup["key"] == ["entity_id", "estimate_date", "period_type"]

    def test_load_strategy_overwrite_iceberg(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        load = config["bronze_to_silver"]["load_strategy"]
        assert load["mode"] == "overwrite"
        assert load["target_format"] == "iceberg"

    def test_no_silver_to_gold(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        assert "silver_to_gold" not in config


class TestQualityConfig:
    def test_silver_threshold(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        assert config["quality"]["silver_threshold"] >= 0.80

    def test_period_type_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        period_rule = next(r for r in validity if r.get("column") == "period_type")
        assert period_rule["severity"] == "critical"

    def test_num_analysts_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        rule = next(r for r in validity if r.get("column") == "num_analysts")
        assert rule["severity"] == "critical"

    def test_eps_range_warning_only(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        custom_rules = [r for r in validity if "CustomSql" in r.get("rule", "") and "eps_low" in r.get("rule", "")]
        assert custom_rules and custom_rules[0]["severity"] == "warning"

    def test_fk_check_warning(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        consistency = config["dimensions"]["consistency"]
        assert any(
            r.get("severity") == "warning" and "silver_entity_resolved" in r.get("rule", "")
            for r in consistency
        )

    def test_pk_uniqueness_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        u = config["dimensions"]["uniqueness"]
        assert u[0]["columns"] == ["entity_id", "estimate_date", "period_type"]
        assert u[0]["severity"] == "critical"


class TestScripts:
    def test_scripts_exist(self):
        assert (SCRIPTS_DIR / "extract" / "ingest_to_bronze.py").exists()
        assert (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").exists()
        assert (SCRIPTS_DIR / "quality" / "run_quality_checks.py").exists()

    def test_silver_uses_lineage_routing(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "enable-data-lineage" in s or "lineage" in s

    def test_silver_reads_from_catalog(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "from_catalog" in s

    def test_silver_writes_iceberg(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "iceberg" in s.lower()

    def test_silver_dedups_on_pk(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert 'partitionBy("entity_id", "estimate_date", "period_type")' in s

    def test_silver_filters_period_type(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert '"NTM"' in s and '"FY1"' in s and '"FY2"' in s

    def test_scripts_use_structured_logger(self):
        for path in [
            SCRIPTS_DIR / "extract" / "ingest_to_bronze.py",
            SCRIPTS_DIR / "transform" / "bronze_to_silver.py",
            SCRIPTS_DIR / "quality" / "run_quality_checks.py",
        ]:
            assert "StructuredLogger" in path.read_text()


class TestDAG:
    DAG_FILE = "estimates_eps_pipeline.py"

    def test_dag_exists(self):
        assert (DAGS_DIR / self.DAG_FILE).exists()

    def test_required_flags(self):
        d = (DAGS_DIR / self.DAG_FILE).read_text()
        assert "catchup=False" in d
        assert "max_active_runs=1" in d
        assert '"retries": 3' in d
        assert "schedule=None" in d
        assert "TaskGroup" in d
        assert "default_var" in d
        assert '"--enable-data-lineage": "true"' in d
        assert '"--run_id"' in d
        assert "on_failure_callback" in d


class TestSQL:
    def test_bronze_partitioned_by_ingestion_date(self):
        sql = (SQL_DIR / "bronze" / "create_bronze_table.sql").read_text()
        assert "PARTITIONED BY (ingestion_date" in sql

    def test_silver_uses_iceberg(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        assert "USING iceberg" in sql

    def test_silver_pk_columns_not_null(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        for col in ("entity_id", "estimate_date", "period_type"):
            line = next(line for line in sql.splitlines() if line.strip().startswith(col + " "))
            assert "NOT NULL" in line, f"{col} must be NOT NULL"


class TestToolRoutingDecisions:
    def test_bronze_routing(self):
        s = (SCRIPTS_DIR / "extract" / "ingest_to_bronze.py").read_text()
        assert "s3-copy-sync" in s or "core" in s

    def test_silver_routing(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "glue-etl-iceberg-silver" in s or "glue-athena" in s

    def test_quality_routing(self):
        s = (SCRIPTS_DIR / "quality" / "run_quality_checks.py").read_text()
        assert "glue-data-quality" in s or "glue-athena" in s
