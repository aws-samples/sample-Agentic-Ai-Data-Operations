"""Unit tests for supplier_chain_data."""

from pathlib import Path

import pytest
import yaml


WORKLOAD_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"
SCRIPTS_DIR = WORKLOAD_DIR / "scripts"
DAGS_DIR = WORKLOAD_DIR / "dags"
SQL_DIR = WORKLOAD_DIR / "sql"

PK = ["buyer_ticker", "supplier_ticker", "effective_date", "product_category"]


class TestSourceConfig:
    def test_dedup_key(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["ingestion"]["dedup_key"] == PK

    def test_manual_schedule(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert config["ingestion"]["schedule"] is None
        assert config["source"]["frequency"] == "ad_hoc"


class TestSemanticConfig:
    def test_pii_columns_flagged(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        pii_cols = {c["name"]: c for c in config["columns"] if c.get("pii")}
        assert "contact_email" in pii_cols
        assert pii_cols["contact_email"]["pii_type"] == "EMAIL"
        assert pii_cols["contact_email"]["sensitivity"] == "HIGH"
        assert "supplier_address" in pii_cols
        assert pii_cols["supplier_address"]["pii_type"] == "ADDRESS"

    def test_buyer_ticker_fk_warning(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        buyer = next(c for c in config["columns"] if c["name"] == "buyer_ticker")
        rel = buyer.get("relationship", {})
        assert rel.get("target_table") == "silver_entity_resolved"
        assert rel.get("target_column") == "ticker"
        assert rel.get("enforcement") == "warning"


class TestTransformationConfig:
    def test_dedup_keep_latest(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        dedup = config["bronze_to_silver"]["deduplication"]
        assert dedup["strategy"] == "keep_latest"
        assert dedup["key"] == PK

    def test_quarantine_for_bad_data(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        validation = config["bronze_to_silver"]["validation"]
        # Effective date and concentration must be quarantined.
        date_rule = next(r for r in validation if r["column"] == "effective_date")
        assert date_rule["action"] == "quarantine"
        conc_rule = next(r for r in validation if r["column"] == "supply_concentration_pct")
        assert conc_rule["action"] == "quarantine"
        assert "0 AND 100" in conc_rule["rule"] or "0 and 100" in conc_rule["rule"].lower()


class TestQualityConfig:
    def test_silver_threshold(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        assert config["quality"]["silver_threshold"] >= 0.80

    def test_pk_uniqueness_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        u = config["dimensions"]["uniqueness"]
        assert u[0]["columns"] == PK
        assert u[0]["severity"] == "critical"

    def test_concentration_range_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        rule = next(r for r in validity if r.get("column") == "supply_concentration_pct")
        assert rule["severity"] == "critical"
        assert "between 0 and 100" in rule["rule"]

    def test_contract_value_nonneg_critical(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        validity = config["dimensions"]["validity"]
        rule = next(r for r in validity if r.get("column") == "contract_value_usd")
        assert rule["severity"] == "critical"

    def test_buyer_ticker_fk_warning(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        consistency = config["dimensions"]["consistency"]
        assert any(
            r.get("severity") == "warning" and "buyer_ticker" in r.get("rule", "") and "silver_entity_resolved" in r.get("rule", "")
            for r in consistency
        )

    def test_pii_rules_present(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        assert "pii_rules" in config
        detected = {c["column"]: c for c in config["pii_rules"]["detected_columns"]}
        assert detected["contact_email"]["type"] == "EMAIL"
        assert detected["supplier_address"]["type"] == "ADDRESS"
        lf_tags = {t["tag"]: t for t in config["pii_rules"]["lf_tags"]}
        assert lf_tags["PII_Classification"]["value"] == "CONTAINS_PII"
        assert "EMAIL" in lf_tags["PII_Type"]["values"]
        assert "ADDRESS" in lf_tags["PII_Type"]["values"]
        assert lf_tags["Data_Sensitivity"]["value"] == "HIGH"


class TestScripts:
    def test_silver_dedups_on_pk(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert (
            'partitionBy(\n    "buyer_ticker", "supplier_ticker", "effective_date", "product_category"\n)'
            in s
        )

    def test_silver_quarantines_bad_data(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "supply_concentration_pct" in s
        assert "< 0" in s and "> 100" in s
        assert "effective_date" in s and "isNull" in s

    def test_silver_uses_lineage_routing(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "enable-data-lineage" in s or "lineage" in s

    def test_silver_writes_iceberg(self):
        s = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "iceberg" in s.lower()

    def test_quality_enforces_critical_numerics(self):
        s = (SCRIPTS_DIR / "quality" / "run_quality_checks.py").read_text()
        assert "supply_concentration_pct" in s
        assert "contract_value_usd" in s

    def test_scripts_use_structured_logger(self):
        for path in [
            SCRIPTS_DIR / "extract" / "ingest_to_bronze.py",
            SCRIPTS_DIR / "transform" / "bronze_to_silver.py",
            SCRIPTS_DIR / "quality" / "run_quality_checks.py",
        ]:
            assert "StructuredLogger" in path.read_text()


class TestDAG:
    DAG_FILE = "supplier_chain_data_pipeline.py"

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

    def test_dag_has_pii_tagging_step(self):
        d = (DAGS_DIR / self.DAG_FILE).read_text()
        assert "pii_tagging" in d


class TestSQL:
    def test_silver_uses_iceberg(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        assert "USING iceberg" in sql

    def test_silver_pk_columns_not_null(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        for col in ("buyer_ticker", "supplier_ticker", "effective_date",
                    "product_category", "relationship_type"):
            line = next(line for line in sql.splitlines() if line.strip().startswith(col + " "))
            assert "NOT NULL" in line

    def test_silver_pii_columns_present(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        # PII columns must be in Silver — they're tagged via Lake Formation, not dropped.
        assert "contact_email" in sql
        assert "supplier_address" in sql


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

    def test_pii_tagging_routing(self):
        d = (DAGS_DIR / "supplier_chain_data_pipeline.py").read_text()
        assert "lake-formation-grant" in d or "lakeformation" in d
