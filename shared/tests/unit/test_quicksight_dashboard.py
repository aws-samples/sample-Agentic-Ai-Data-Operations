"""
Unit tests for shared/utils/quicksight_dashboard.py

Tests config validation and QuickSight API payload generation
against the analytics.yaml from workloads/customer_master/config/.
"""

from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ANALYTICS_YAML = PROJECT_ROOT / "workloads" / "customer_master" / "config" / "analytics.yaml"

# Import module under test
import sys
sys.path.insert(0, str(PROJECT_ROOT))
from shared.utils.quicksight_dashboard import (
    generate_dashboard_definition,
    validate_analytics_config,
    _map_column_type,
    _build_filter_definitions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load the real analytics.yaml for testing."""
    with open(ANALYTICS_YAML, "r") as f:
        return yaml.safe_load(f)


def _write_temp_yaml(data: dict) -> str:
    """Write a dict as YAML to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    return path


# ===========================================================================
# validate_analytics_config tests
# ===========================================================================

class TestValidateAnalyticsConfig:
    """Tests for validate_analytics_config()."""

    def test_valid_config_returns_no_errors(self):
        """The real analytics.yaml should pass validation."""
        errors = validate_analytics_config(str(ANALYTICS_YAML))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_file_returns_error(self):
        errors = validate_analytics_config("/nonexistent/path/analytics.yaml")
        assert len(errors) == 1
        assert "not found" in errors[0].lower()

    def test_invalid_yaml_returns_error(self):
        fd, path = tempfile.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(":\n  - [invalid\n  yaml:")
            errors = validate_analytics_config(path)
            assert len(errors) >= 1
            assert any("parse" in e.lower() or "yaml" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_missing_top_level_keys(self):
        config = {"dashboard": {"name": "test", "display_name": "Test", "description": "Test"}}
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("missing top-level" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_missing_dashboard_keys(self):
        config = _load_config()
        del config["dashboard"]["name"]
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("dashboard" in e.lower() and "name" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_empty_datasets_returns_error(self):
        config = _load_config()
        config["datasets"] = []
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("datasets" in e.lower() and "non-empty" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_duplicate_dataset_id(self):
        config = _load_config()
        config["datasets"].append(copy.deepcopy(config["datasets"][0]))
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("duplicate" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_import_mode(self):
        config = _load_config()
        config["datasets"][0]["import_mode"] = "INVALID_MODE"
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("import_mode" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_missing_dataset_keys(self):
        config = _load_config()
        del config["datasets"][0]["source_table"]
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("source_table" in e for e in errors)
        finally:
            os.unlink(path)

    def test_empty_visuals_returns_error(self):
        config = _load_config()
        config["visuals"] = []
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("visuals" in e.lower() and "non-empty" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_duplicate_visual_id(self):
        config = _load_config()
        config["visuals"].append(copy.deepcopy(config["visuals"][0]))
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("duplicate" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_visual_type(self):
        config = _load_config()
        config["visuals"][0]["type"] = "INVALID_CHART"
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("type" in e.lower() and "invalid" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_visual_references_nonexistent_dataset(self):
        config = _load_config()
        config["visuals"][0]["dataset_id"] = "nonexistent_dataset"
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("not found" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_table_visual_with_null_dataset_needs_custom_sql(self):
        config = _load_config()
        # Find the TABLE visual and remove custom_sql
        for vis in config["visuals"]:
            if vis["type"] == "TABLE":
                vis["dataset_id"] = None
                vis.pop("custom_sql", None)
                break
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("custom_sql" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_empty_permissions_returns_error(self):
        config = _load_config()
        config["permissions"] = []
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("permissions" in e.lower() and "non-empty" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_permission_role(self):
        config = _load_config()
        config["permissions"][0]["role"] = "SUPERADMIN"
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("role" in e.lower() and "invalid" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_missing_permission_keys(self):
        config = _load_config()
        del config["permissions"][0]["actions"]
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("actions" in e for e in errors)
        finally:
            os.unlink(path)

    def test_missing_refresh_cron(self):
        config = _load_config()
        del config["refresh"]["schedule"]["cron"]
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("cron" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_non_dict_top_level(self):
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            f.write("- just\n- a\n- list\n")
        try:
            errors = validate_analytics_config(path)
            assert any("mapping" in e.lower() or "dict" in e.lower() for e in errors)
        finally:
            os.unlink(path)

    def test_missing_column_keys_in_dataset(self):
        config = _load_config()
        # Remove 'type' from first column of first dataset
        config["datasets"][0]["columns"][0] = {"name": "only_name"}
        path = _write_temp_yaml(config)
        try:
            errors = validate_analytics_config(path)
            assert any("columns" in e.lower() and "type" in e.lower() for e in errors)
        finally:
            os.unlink(path)


# ===========================================================================
# generate_dashboard_definition tests
# ===========================================================================

class TestGenerateDashboardDefinition:
    """Tests for generate_dashboard_definition()."""

    def test_generates_valid_payload(self):
        """Should produce a well-structured QuickSight API payload."""
        payload = generate_dashboard_definition(
            str(ANALYTICS_YAML),
            aws_account_id="123456789012",
            data_source_arn="arn:aws:quicksight:us-east-1:123456789012:datasource/athena-gold",
        )
        assert isinstance(payload, dict)
        assert payload["AwsAccountId"] == "123456789012"
        assert payload["DashboardId"] == "customer-order-analytics"
        assert payload["Name"] == "Customer & Order Analytics"

    def test_payload_contains_definition(self):
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        assert "Definition" in payload
        definition = payload["Definition"]
        assert "DataSetIdentifierDeclarations" in definition
        assert "Sheets" in definition
        assert "FilterDefinitions" in definition

    def test_dataset_declarations_match_config(self):
        config = _load_config()
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        declarations = payload["Definition"]["DataSetIdentifierDeclarations"]
        config_ids = {ds["id"] for ds in config["datasets"]}
        payload_ids = {d["Identifier"] for d in declarations}
        assert config_ids == payload_ids

    def test_visuals_count_matches_config(self):
        config = _load_config()
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        sheets = payload["Definition"]["Sheets"]
        assert len(sheets) == 1
        visual_count = len(sheets[0]["Visuals"])
        assert visual_count == len(config["visuals"])

    def test_eight_visuals_present(self):
        """Dashboard should have exactly 8 visuals."""
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        visuals = payload["Definition"]["Sheets"][0]["Visuals"]
        assert len(visuals) == 8

    def test_permissions_in_payload(self):
        payload = generate_dashboard_definition(
            str(ANALYTICS_YAML), aws_account_id="123456789012"
        )
        permissions = payload["Permissions"]
        assert len(permissions) == 2
        principals = [p["Principal"] for p in permissions]
        assert any("analytics-viewers" in p for p in principals)
        assert any("analytics-authors" in p for p in principals)

    def test_tags_include_workload(self):
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        tags = payload["Tags"]
        tag_keys = {t["Key"]: t["Value"] for t in tags}
        assert tag_keys.get("workload") == "customer-order-analytics"
        assert tag_keys.get("managed-by") == "data-onboarding-agent"

    def test_spice_refresh_schedule(self):
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        assert "_RefreshSchedule" in payload
        refresh = payload["_RefreshSchedule"]
        assert refresh["Cron"] == "0 8 * * *"
        assert "customer_summary" in refresh["DataSetIds"]
        assert "order_metrics" in refresh["DataSetIds"]
        # DIRECT_QUERY datasets should NOT be in refresh
        assert "customer_fact" not in refresh["DataSetIds"]
        assert "order_fact" not in refresh["DataSetIds"]

    def test_grid_layout_elements(self):
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        layouts = payload["Definition"]["Sheets"][0]["Layouts"]
        assert len(layouts) == 1
        elements = layouts[0]["Configuration"]["GridLayout"]["Elements"]
        assert len(elements) == 8
        # Check that each element has required position fields
        for elem in elements:
            assert "ElementId" in elem
            assert "ColumnIndex" in elem
            assert "RowIndex" in elem
            assert "ColumnSpan" in elem
            assert "RowSpan" in elem

    def test_dataset_definitions_present(self):
        payload = generate_dashboard_definition(
            str(ANALYTICS_YAML),
            aws_account_id="123456789012",
            data_source_arn="arn:aws:quicksight:us-east-1:123456789012:datasource/athena-gold",
        )
        ds_defs = payload["_DataSetDefinitions"]
        assert len(ds_defs) == 4
        ds_ids = {d["DataSetId"] for d in ds_defs}
        assert ds_ids == {"customer_summary", "order_metrics", "customer_fact", "order_fact"}

    def test_dataset_import_modes(self):
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        ds_defs = payload["_DataSetDefinitions"]
        modes = {d["DataSetId"]: d["ImportMode"] for d in ds_defs}
        assert modes["customer_summary"] == "SPICE"
        assert modes["order_metrics"] == "SPICE"
        assert modes["customer_fact"] == "DIRECT_QUERY"
        assert modes["order_fact"] == "DIRECT_QUERY"

    def test_placeholder_account_id_when_none(self):
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        assert payload["AwsAccountId"] == "PLACEHOLDER_ACCOUNT_ID"

    def test_publish_options(self):
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        opts = payload["DashboardPublishOptions"]
        assert opts["AdHocFilteringOption"]["AvailabilityStatus"] == "ENABLED"
        assert opts["ExportToCSVOption"]["AvailabilityStatus"] == "ENABLED"

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            generate_dashboard_definition("/nonexistent/analytics.yaml")

    def test_raises_on_invalid_config(self):
        config = _load_config()
        del config["visuals"]
        path = _write_temp_yaml(config)
        try:
            with pytest.raises(ValueError, match="validation failed"):
                generate_dashboard_definition(path)
        finally:
            os.unlink(path)

    def test_filter_definitions_extracted(self):
        payload = generate_dashboard_definition(str(ANALYTICS_YAML))
        filters = payload["Definition"]["FilterDefinitions"]
        # Should have filters from visuals that specify non-null column filters
        assert isinstance(filters, list)
        assert len(filters) > 0
        # Check filter structure
        for filt in filters:
            assert "FilterId" in filt
            assert "Column" in filt
            assert "Scope" in filt


# ===========================================================================
# Helper function tests
# ===========================================================================

class TestMapColumnType:
    """Tests for _map_column_type()."""

    def test_string_maps_to_string(self):
        assert _map_column_type("STRING") == "STRING"

    def test_integer_maps_to_integer(self):
        assert _map_column_type("INTEGER") == "INTEGER"

    def test_decimal_maps_to_decimal(self):
        assert _map_column_type("DECIMAL") == "DECIMAL"

    def test_date_maps_to_datetime(self):
        assert _map_column_type("DATE") == "DATETIME"

    def test_unknown_type_defaults_to_string(self):
        assert _map_column_type("UNKNOWN") == "STRING"

    def test_case_insensitive(self):
        assert _map_column_type("string") == "STRING"
        assert _map_column_type("Integer") == "INTEGER"


class TestBuildFilterDefinitions:
    """Tests for _build_filter_definitions()."""

    def test_filters_from_visuals_with_filters(self):
        visuals = [
            {
                "id": "test_vis",
                "filters": [
                    {"column": "status", "operator": "EQUALS", "values": ["Active"]},
                ],
            }
        ]
        filters = _build_filter_definitions(visuals)
        assert len(filters) == 1
        assert filters[0]["FilterId"] == "test_vis_status"
        assert filters[0]["Column"] == "status"

    def test_skips_null_column_filters(self):
        visuals = [
            {
                "id": "test_vis",
                "filters": [
                    {"column": None, "operator": None, "values": []},
                ],
            }
        ]
        filters = _build_filter_definitions(visuals)
        assert len(filters) == 0

    def test_no_filters_returns_empty(self):
        visuals = [{"id": "test_vis", "filters": []}]
        filters = _build_filter_definitions(visuals)
        assert filters == []

    def test_missing_filters_key(self):
        visuals = [{"id": "test_vis"}]
        filters = _build_filter_definitions(visuals)
        assert filters == []


# ===========================================================================
# analytics.yaml structure tests (config content validation)
# ===========================================================================

class TestAnalyticsYamlContent:
    """Tests that analytics.yaml has the expected content for the dashboard spec."""

    @pytest.fixture(autouse=True)
    def load_config(self):
        self.config = _load_config()

    def test_dashboard_name(self):
        assert self.config["dashboard"]["name"] == "customer-order-analytics"

    def test_dashboard_has_source_workloads(self):
        workloads = self.config["dashboard"]["source_workloads"]
        assert "customer_master" in workloads
        assert "order_transactions" in workloads

    def test_four_datasets(self):
        assert len(self.config["datasets"]) == 4

    def test_spice_datasets(self):
        spice = [ds for ds in self.config["datasets"] if ds["import_mode"] == "SPICE"]
        assert len(spice) == 2
        spice_ids = {ds["id"] for ds in spice}
        assert spice_ids == {"customer_summary", "order_metrics"}

    def test_direct_query_datasets(self):
        dq = [ds for ds in self.config["datasets"] if ds["import_mode"] == "DIRECT_QUERY"]
        assert len(dq) == 2
        dq_ids = {ds["id"] for ds in dq}
        assert dq_ids == {"customer_fact", "order_fact"}

    def test_eight_visuals(self):
        assert len(self.config["visuals"]) == 8

    def test_visual_types(self):
        types = {vis["type"] for vis in self.config["visuals"]}
        expected = {"KPI", "BAR_CHART", "LINE_CHART", "PIE_CHART", "HORIZONTAL_BAR_CHART", "HEAT_MAP", "TABLE"}
        assert types == expected

    def test_kpi_visuals(self):
        kpis = [v for v in self.config["visuals"] if v["type"] == "KPI"]
        assert len(kpis) == 2
        titles = {k["title"] for k in kpis}
        assert "Total Customers" in titles
        assert "Total Revenue" in titles

    def test_customer_ltv_table_has_custom_sql(self):
        table = next(v for v in self.config["visuals"] if v["type"] == "TABLE")
        assert table["custom_sql"] is not None
        assert "customer_id" in table["custom_sql"]
        assert "order_fact" in table["custom_sql"]
        assert "LIMIT 20" in table["custom_sql"]

    def test_two_permission_groups(self):
        assert len(self.config["permissions"]) == 2
        roles = {p["role"] for p in self.config["permissions"]}
        assert roles == {"VIEWER", "AUTHOR"}

    def test_viewer_group(self):
        viewer = next(p for p in self.config["permissions"] if p["role"] == "VIEWER")
        assert viewer["principal_name"] == "analytics-viewers"
        assert "quicksight:QueryDashboard" in viewer["actions"]

    def test_author_group(self):
        author = next(p for p in self.config["permissions"] if p["role"] == "AUTHOR")
        assert author["principal_name"] == "analytics-authors"
        assert "quicksight:UpdateDashboard" in author["actions"]

    def test_refresh_cron_at_8am(self):
        assert self.config["refresh"]["schedule"]["cron"] == "0 8 * * *"

    def test_refresh_only_spice_datasets(self):
        refresh_ds = self.config["refresh"]["datasets"]
        modes = {ds["dataset_id"]: ds["import_mode"] for ds in refresh_ds}
        for ds_id, mode in modes.items():
            assert mode == "SPICE", f"{ds_id} should be SPICE in refresh schedule"

    def test_cross_workload_join_defined(self):
        joins = self.config["dashboard"]["joins"]
        assert len(joins) == 1
        assert joins[0]["left_column"] == "customer_id"
        assert joins[0]["right_column"] == "customer_id"
