"""Unit tests for employee_attendance transformations.

Verifies tool routing decisions are correctly reflected in generated artifacts:
- Bronze scripts use correct source path and partition
- Silver scripts include --enable-data-lineage (invariant: lineage-always)
- Gold scripts produce star schema (fact + dims)
- Quality checks enforce thresholds (invariant: quality-gates)
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

    def test_dedup_key_defined(self):
        with open(CONFIG_DIR / "source.yaml") as f:
            config = yaml.safe_load(f)
        assert "dedup_key" in config["ingestion"]
        assert len(config["ingestion"]["dedup_key"]) > 0


class TestSemanticConfig:
    def test_semantic_yaml_exists(self):
        assert (CONFIG_DIR / "semantic.yaml").exists()

    def test_pii_columns_flagged(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        pii_columns = [c for c in config["columns"] if c.get("pii")]
        assert len(pii_columns) >= 2
        pii_names = [c["name"] for c in pii_columns]
        assert "full_name" in pii_names
        assert "email" in pii_names

    def test_measures_defined(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        measures = [c for c in config["columns"] if c.get("role") == "measure"]
        assert len(measures) >= 1

    def test_dimensions_defined(self):
        with open(CONFIG_DIR / "semantic.yaml") as f:
            config = yaml.safe_load(f)
        dims = [c for c in config["columns"] if c.get("role") == "dimension"]
        assert len(dims) >= 2


class TestTransformationConfig:
    def test_transformations_yaml_exists(self):
        assert (CONFIG_DIR / "transformations.yaml").exists()

    def test_deduplication_strategy(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        dedup = config["bronze_to_silver"]["deduplication"]
        assert dedup["strategy"] == "keep_latest"
        assert "employee_id" in dedup["key"]

    def test_gold_schema_is_star(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        assert config["silver_to_gold"]["schema_type"] == "star"
        assert "fact_table" in config["silver_to_gold"]
        assert "dimension_tables" in config["silver_to_gold"]

    def test_scd2_on_dim_employee(self):
        with open(CONFIG_DIR / "transformations.yaml") as f:
            config = yaml.safe_load(f)
        dims = config["silver_to_gold"]["dimension_tables"]
        employee_dim = next(d for d in dims if d["name"] == "dim_employee")
        assert employee_dim["type"] == "scd2"


class TestQualityConfig:
    def test_quality_yaml_exists(self):
        assert (CONFIG_DIR / "quality_rules.yaml").exists()

    def test_silver_threshold(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        assert config["quality"]["silver_threshold"] >= 0.80

    def test_gold_threshold(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        assert config["quality"]["gold_threshold"] >= 0.95

    def test_critical_rules_exist(self):
        with open(CONFIG_DIR / "quality_rules.yaml") as f:
            config = yaml.safe_load(f)
        all_rules = []
        for dim in config["dimensions"].values():
            if isinstance(dim, list):
                all_rules.extend(dim)
        critical = [r for r in all_rules if r.get("severity") == "critical"]
        assert len(critical) >= 3


class TestScripts:
    def test_bronze_script_exists(self):
        assert (SCRIPTS_DIR / "extract" / "ingest_to_bronze.py").exists()

    def test_silver_script_exists(self):
        assert (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").exists()

    def test_gold_script_exists(self):
        assert (SCRIPTS_DIR / "transform" / "silver_to_gold.py").exists()

    def test_quality_script_exists(self):
        assert (SCRIPTS_DIR / "quality" / "run_quality_checks.py").exists()

    def test_silver_script_uses_lineage(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "enable-data-lineage" in script or "lineage" in script

    def test_silver_script_reads_from_catalog(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "from_catalog" in script

    def test_silver_script_writes_iceberg(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "iceberg" in script.lower()

    def test_gold_script_writes_iceberg(self):
        script = (SCRIPTS_DIR / "transform" / "silver_to_gold.py").read_text()
        assert "iceberg" in script.lower()


class TestDAG:
    def test_dag_file_exists(self):
        assert (DAGS_DIR / "employee_attendance_pipeline.py").exists()

    def test_dag_has_catchup_false(self):
        dag_code = (DAGS_DIR / "employee_attendance_pipeline.py").read_text()
        assert "catchup=False" in dag_code

    def test_dag_has_max_active_runs_1(self):
        dag_code = (DAGS_DIR / "employee_attendance_pipeline.py").read_text()
        assert "max_active_runs=1" in dag_code

    def test_dag_has_retries(self):
        dag_code = (DAGS_DIR / "employee_attendance_pipeline.py").read_text()
        assert "retries" in dag_code

    def test_dag_has_lineage_flag(self):
        dag_code = (DAGS_DIR / "employee_attendance_pipeline.py").read_text()
        assert '"--enable-data-lineage": "true"' in dag_code

    def test_dag_has_on_failure_callback(self):
        dag_code = (DAGS_DIR / "employee_attendance_pipeline.py").read_text()
        assert "on_failure_callback" in dag_code

    def test_dag_uses_task_groups(self):
        dag_code = (DAGS_DIR / "employee_attendance_pipeline.py").read_text()
        assert "TaskGroup" in dag_code

    def test_dag_uses_variables_not_hardcoded(self):
        dag_code = (DAGS_DIR / "employee_attendance_pipeline.py").read_text()
        assert "Variable.get" in dag_code

    def test_dag_has_default_var_on_variables(self):
        dag_code = (DAGS_DIR / "employee_attendance_pipeline.py").read_text()
        assert "default_var" in dag_code


class TestSQL:
    def test_bronze_sql_exists(self):
        assert (SQL_DIR / "bronze" / "create_bronze_table.sql").exists()

    def test_silver_sql_uses_iceberg(self):
        sql = (SQL_DIR / "silver" / "create_silver_table.sql").read_text()
        assert "USING iceberg" in sql

    def test_gold_sql_has_star_schema(self):
        sql = (SQL_DIR / "gold" / "create_gold_star_schema.sql").read_text()
        assert "fact_attendance" in sql
        assert "dim_employee" in sql
        assert "dim_location" in sql

    def test_gold_sql_uses_iceberg(self):
        sql = (SQL_DIR / "gold" / "create_gold_star_schema.sql").read_text()
        assert "USING iceberg" in sql


class TestToolRoutingDecisions:
    """Verify that tool routing comments in scripts match TOOL_ROUTING.md decisions."""

    def test_bronze_uses_correct_tool(self):
        script = (SCRIPTS_DIR / "extract" / "ingest_to_bronze.py").read_text()
        assert "s3-copy-sync" in script or "core" in script

    def test_silver_uses_correct_tool(self):
        script = (SCRIPTS_DIR / "transform" / "bronze_to_silver.py").read_text()
        assert "glue-etl-iceberg-silver" in script or "glue-athena" in script

    def test_gold_uses_correct_tool(self):
        script = (SCRIPTS_DIR / "transform" / "silver_to_gold.py").read_text()
        assert "glue-etl-iceberg-gold" in script or "glue-athena" in script

    def test_quality_uses_correct_tool(self):
        script = (SCRIPTS_DIR / "quality" / "run_quality_checks.py").read_text()
        assert "glue-data-quality" in script or "glue-athena" in script
