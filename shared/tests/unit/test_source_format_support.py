"""Cross-platform source-format contract and Bronze reader coverage."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
FORMAT_CASES = {
    "xml": {"row_tag": "customer"},
    "log": {"log_type": "nginx", "multiline": False, "encoding": "utf-8"},
}


def _schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bronze_spec(source_format: str, options: dict, *, schema_version: str) -> dict:
    spec = {
        "dataset_name": "format_probe",
        "schema_version": schema_version,
        "source_path": "s3://example-bucket/input/",
        "source_format": source_format,
        "landing_zone": "s3://example-bucket/bronze/",
        "format_options": options,
    }
    if schema_version == "v2":
        spec.update(
            {
                "catalog_database": "format_probe_db",
                "catalog_table": "bronze_format_probe",
                "idempotency_key": "source_path",
            }
        )
    return spec


def test_xml_and_log_are_valid_bronze_formats_on_all_surfaces():
    schema_paths = (
        ROOT / "contracts/v2/bronze_spec.schema.json",
        ROOT / "plugins/claude-code/lib/contracts/v1/bronze_spec.schema.json",
        ROOT / "adapters/claude-code/plugins/claude-code/lib/contracts/v1/bronze_spec.schema.json",
    )

    for schema_path in schema_paths:
        schema = _schema(schema_path)
        for source_format, options in FORMAT_CASES.items():
            errors = list(
                Draft202012Validator(schema).iter_errors(
                    _bronze_spec(
                        source_format,
                        options,
                        schema_version="v2" if "/v2/" in str(schema_path) else "v1",
                    )
                )
            )
            assert not errors, f"{schema_path}: {errors}"


def test_source_contracts_advertise_xml_and_log():
    schema_paths = (
        ROOT / "contracts/v1/source_profile.schema.json",
        ROOT / "plugins/claude-code/lib/contracts/v1/source_profile.schema.json",
        ROOT / "adapters/claude-code/plugins/claude-code/lib/contracts/v1/source_profile.schema.json",
    )

    for schema_path in schema_paths:
        source = _schema(schema_path)["properties"]["source"]["properties"]
        assert {"xml", "log"} <= set(source["type"]["enum"])
        assert {"xml", "log"} <= set(source["format"]["enum"])
        assert {"row_tag", "log_type"} <= set(
            source["format_options"]["properties"]
        )


def test_all_bronze_templates_have_xml_and_raw_log_readers():
    template_paths = (
        ROOT / "shared/templates/bronze_ingestion.py.j2",
        ROOT / "plugins/claude-code/lib/shared/templates/bronze_ingestion.py.j2",
        ROOT / "adapters/claude-code/plugins/claude-code/lib/shared/templates/bronze_ingestion.py.j2",
    )

    for template_path in template_paths:
        text = template_path.read_text(encoding="utf-8")
        assert 'source_format == "xml"' in text
        assert 'source_format == "log"' in text
        assert 'spark.read.format("xml")' in text
        assert 'spark.read.format("text")' in text
