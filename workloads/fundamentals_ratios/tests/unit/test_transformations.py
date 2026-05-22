"""Unit tests for fundamentals_ratios."""

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
        assert config["ingestion"]["dedup_key"] == ["entity_id", "fiscal_period_id"]

    def test_manual_schedule(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["ingestion"]["schedule"] is None
        assert config["source"]["frequency"] == "ad_hoc"


class TestSemanticConfig:
    def test_dropped_cols_listed(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        dropped = [c["name"] for c in config.get("dropped_columns", [])]
        for col in ("roa", "debt_to_equity", "current_ratio", "load_timestamp"):
            assert col in dropped

    def test_kept_cols_present(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        names = [c["name"] for c in config["columns"]]
        for col in ("pe_ratio", "pb_ratio", "ev_ebitda", "roe"):
            assert col in names

    def test_entity_id_has_fk(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        entity_id = next(c for c in config["columns"] if c["name"] == "entity_id")
        assert entity_id.get("relationship", {}).get("target_table") == "silver_entity_resolved"


class TestTransformationConfig:
    def test_dropped_cols(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        dropped = [d["column"] for d in config["bronze_to_silver"]["dropped_columns"]]
        for col in ("roa", "debt_to_equity", "current_ratio", "load_timestamp"):
            assert col in dropped

    def test_dedup_keep_latest(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        dedup = config["bronze_to_silver"]["deduplication"]
        assert dedup["strategy"] == "keep_latest"


class TestQualityConfig:
    def test_silver_threshold(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        assert config["quality"]["silver_threshold"] >= 0.80

    def test_pk_uniqueness_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        u = config["dimensions"]["uniqueness"]
        assert u[0]["columns"] == ["entity_id", "fiscal_period_id"]
        assert u[0]["severity"] == "critical"

    def test_pe_ratio_warning(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        rule = next(r for r in validity if r.get("column") == "pe_ratio")
        assert rule["severity"] == "warning"

    def test_fk_check_warning(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        consistency = config["dimensions"]["consistency"]
        assert any(
            r.get("severity") == "warning" and "silver_entity_resolved" in r.get("rule", "")
            for r in consistency
        )


class TestScripts:
    def test_silver_drops_empty_columns(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        for col in ("roa", "debt_to_equity", "current_ratio", "load_timestamp"):
            assert col in s

    def test_silver_dedups_on_pk(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert 'partitionBy("entity_id", "fiscal_period_id")' in s

    def test_silver_uses_lineage_routing(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "enable-data-lineage" in s or "lineage" in s

    def test_silver_writes_iceberg(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "iceberg" in s.lower()

    def test_scripts_use_structured_logger(self):
        for path in [
            SCRIPTS_DIR / "extract" / "ingest_to_bronze.py",
            SCRIPTS_DIR / "transform" / "bronze_to_silver.py",
            SCRIPTS_DIR / "quality" / "run_quality_checks.py",
        ]:
            assert "StructuredLogger" in path.read_text()


class TestDAG:
    DAG_FILE = "fundamentals_ratios_pipeline.py"

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
    def test_silver_uses_iceberg(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        assert "USING iceberg" in sql

    def test_silver_no_dropped_cols(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        non_comment = "\n".join(
            line for line in sql.splitlines() if not line.strip().startswith("--")
        ).lower()
        for col in ("roa", "debt_to_equity", "current_ratio", "load_timestamp"):
            assert col not in non_comment, f"Silver SQL must not include dropped column {col}"

    def test_silver_pk_columns_not_null(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        for col in ("entity_id", "fiscal_period_id", "fiscal_year"):
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
