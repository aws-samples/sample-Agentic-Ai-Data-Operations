"""Unit tests for estimates_ratings configs, scripts, DAG, and SQL."""

from pathlib import Path

import pytest
import yaml


WORKLOAD_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"
SCRIPTS_DIR = WORKLOAD_DIR / "scripts"
DAGS_DIR = WORKLOAD_DIR / "dags"
SQL_DIR = WORKLOAD_DIR / "sql"


class TestSourceConfig:
    def test_dedup_key(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["ingestion"]["dedup_key"] == ["entity_id", "rating_date"]

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
        assert dedup["key"] == ["entity_id", "rating_date"]

    def test_load_strategy_overwrite_iceberg(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        load = config["bronze_to_silver"]["load_strategy"]
        assert load["mode"] == "overwrite"
        assert load["target_format"] == "iceberg"


class TestQualityConfig:
    def test_silver_threshold(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        assert config["quality"]["silver_threshold"] >= 0.80

    def test_pk_uniqueness_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        u = config["dimensions"]["uniqueness"]
        assert u[0]["columns"] == ["entity_id", "rating_date"]
        assert u[0]["severity"] == "critical"

    def test_target_price_range_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        rule = next(
            r for r in validity
            if "CustomSql" in r.get("rule", "") and "target_price_low" in r.get("rule", "")
        )
        assert rule["severity"] == "critical"

    def test_total_analysts_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        rule = next(
            r for r in validity
            if "CustomSql" in r.get("rule", "") and "buy_count" in r.get("rule", "")
        )
        assert rule["severity"] == "critical"

    def test_consensus_rating_warning(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        rating_rule = next(r for r in validity if r.get("column") == "consensus_rating")
        assert rating_rule["severity"] == "warning"

    def test_fk_check_warning(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        consistency = config["dimensions"]["consistency"]
        assert any(
            r.get("severity") == "warning" and "silver_entity_resolved" in r.get("rule", "")
            for r in consistency
        )


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
        assert 'partitionBy("entity_id", "rating_date")' in s

    def test_scripts_use_structured_logger(self):
        for path in [
            SCRIPTS_DIR / "extract" / "ingest_to_bronze.py",
            SCRIPTS_DIR / "transform" / "bronze_to_silver.py",
            SCRIPTS_DIR / "quality" / "run_quality_checks.py",
        ]:
            assert "StructuredLogger" in path.read_text()


class TestDAG:
    DAG_FILE = "estimates_ratings_pipeline.py"

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
        for col in ("entity_id", "rating_date", "consensus_rating"):
            line = next(line for line in sql.splitlines() if line.strip().startswith(col + " "))
            assert "NOT NULL" in line


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
