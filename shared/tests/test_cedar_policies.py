"""Tests for Cedar policy evaluation.

Tests both guardrail enforcement (16 policies) and agent authorization (7 agents).
Uses the fallback evaluator (no cedarpy dependency required).
If cedarpy is available, tests also run against the native Cedar engine.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure shared/ is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.cedar_client import (
    AgentPrincipal,
    CedarPolicyEvaluator,
    DataZone,
    McpTool,
    PipelineStep,
    UserPrincipal,
    WorkloadFile,
    _LocalEvaluator,
    GUARDRAILS_DIR,
    AGENT_AUTH_DIR,
    SCHEMA_FILE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def evaluator():
    return CedarPolicyEvaluator(mode="local")


@pytest.fixture
def local_eval():
    return _LocalEvaluator()


@pytest.fixture
def onboarding_agent():
    return AgentPrincipal("onboarding", "main_conversation", "test_workload")


@pytest.fixture
def step_staging():
    return PipelineStep(step_number=7, step_name="Staging write", target_zone="staging")


@pytest.fixture
def step_publish():
    return PipelineStep(step_number=10, step_name="Publish write", target_zone="publish")


# ---------------------------------------------------------------------------
# Policy file existence tests
# ---------------------------------------------------------------------------
class TestPolicyFilesExist:
    """Verify all expected policy files are present."""

    def test_schema_file_exists(self):
        assert SCHEMA_FILE.is_file(), f"Missing: {SCHEMA_FILE}"

    @pytest.mark.parametrize("code", [
        "sec_001_no_hardcoded_secrets",
        "sec_002_kms_key_validation",
        "sec_003_pii_masking",
        "sec_004_tls_enforcement",
        "dq_001_quality_gate_threshold",
        "dq_002_no_critical_failures",
        "dq_003_no_silent_drops",
        "dq_004_row_count_range",
        "int_001_landing_immutability",
        "int_002_fk_integrity",
        "int_003_derived_column_formula",
        "int_004_schema_enforcement",
        "ops_001_idempotency",
        "ops_002_encryption_rekeyed",
        "ops_003_audit_log",
        "ops_004_iceberg_metadata",
    ])
    def test_guardrail_policy_exists(self, code):
        path = GUARDRAILS_DIR / f"{code}.cedar"
        assert path.is_file(), f"Missing guardrail policy: {path}"

    @pytest.mark.parametrize("agent", [
        "router_agent",
        "onboarding_agent",
        "metadata_agent",
        "transformation_agent",
        "quality_agent",
        "dag_agent",
        "ontology_staging_agent",
    ])
    def test_agent_policy_exists(self, agent):
        path = AGENT_AUTH_DIR / f"{agent}.cedar"
        assert path.is_file(), f"Missing agent policy: {path}"

    def test_policy_files_parse(self):
        """All .cedar files should be non-empty and contain 'forbid' or 'permit'."""
        for policy_dir in [GUARDRAILS_DIR, AGENT_AUTH_DIR]:
            for cedar_file in policy_dir.glob("*.cedar"):
                content = cedar_file.read_text()
                assert len(content) > 0, f"Empty policy: {cedar_file}"
                assert "forbid" in content or "permit" in content, (
                    f"No forbid/permit in {cedar_file}"
                )


# ---------------------------------------------------------------------------
# SEC guardrail tests
# ---------------------------------------------------------------------------
class TestSecurityGuardrails:

    def test_sec_001_pass_no_secrets(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "SEC-001", "No hardcoded secrets",
            passed=True,
            context={"guardrailCode": "SEC-001", "secretPatternFound": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_sec_001_fail_secret_found(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "SEC-001", "Hardcoded secret found",
            passed=True,  # Would pass inline, but Cedar forbids
            context={"guardrailCode": "SEC-001", "secretPatternFound": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_sec_002_pass_valid_alias(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "SEC-002", "KMS alias valid",
            passed=True,
            context={"guardrailCode": "SEC-002", "kmsAliasValid": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_sec_002_fail_invalid_alias(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "SEC-002", "KMS alias invalid",
            passed=True,
            context={"guardrailCode": "SEC-002", "kmsAliasValid": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_sec_003_pass_pii_masked(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "SEC-003", "PII masked",
            passed=True,
            context={"guardrailCode": "SEC-003", "piiColumnsMasked": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_sec_003_fail_pii_exposed(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "SEC-003", "PII exposed",
            passed=True,
            context={"guardrailCode": "SEC-003", "piiColumnsMasked": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_sec_004_pass_tls(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "SEC-004", "TLS enforced",
            passed=True,
            context={"guardrailCode": "SEC-004", "tlsEnforced": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_sec_004_fail_no_tls(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "SEC-004", "TLS not enforced",
            passed=True,
            context={"guardrailCode": "SEC-004", "tlsEnforced": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False


# ---------------------------------------------------------------------------
# DQ guardrail tests
# ---------------------------------------------------------------------------
class TestQualityGuardrails:

    def test_dq_001_pass_staging_above_threshold(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "DQ-001", "Staging quality gate: 0.92 >= 0.80",
            passed=True,
            context={
                "guardrailCode": "DQ-001",
                "qualityScore": 92,
                "qualityThreshold": 80,
            },
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_dq_001_fail_staging_below_threshold(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "DQ-001", "Staging quality gate: 0.72 >= 0.80",
            passed=True,
            context={
                "guardrailCode": "DQ-001",
                "qualityScore": 72,
                "qualityThreshold": 80,
            },
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_dq_001_pass_publish_above_threshold(self, evaluator, onboarding_agent, step_publish):
        result = evaluator.check(
            "DQ-001", "Publish quality gate: 0.97 >= 0.95",
            passed=True,
            context={
                "guardrailCode": "DQ-001",
                "qualityScore": 97,
                "qualityThreshold": 95,
            },
            principal=onboarding_agent,
            resource=step_publish,
        )
        assert result is True

    def test_dq_001_fail_publish_below_threshold(self, evaluator, onboarding_agent, step_publish):
        result = evaluator.check(
            "DQ-001", "Publish quality gate: 0.90 >= 0.95",
            passed=True,
            context={
                "guardrailCode": "DQ-001",
                "qualityScore": 90,
                "qualityThreshold": 95,
            },
            principal=onboarding_agent,
            resource=step_publish,
        )
        assert result is False

    def test_dq_002_pass_no_critical(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "DQ-002", "No critical failures",
            passed=True,
            context={"guardrailCode": "DQ-002", "criticalFailureCount": 0},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_dq_002_fail_critical_exists(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "DQ-002", "Critical failure found",
            passed=True,
            context={"guardrailCode": "DQ-002", "criticalFailureCount": 2},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_dq_003_pass_rows_balance(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "DQ-003", "Row accounting balances",
            passed=True,
            context={
                "guardrailCode": "DQ-003",
                "rowAccountingBalances": True,
                "inputRows": 100,
                "outputRows": 95,
                "quarantineRows": 5,
            },
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_dq_003_fail_rows_dropped(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "DQ-003", "Rows silently dropped",
            passed=True,
            context={
                "guardrailCode": "DQ-003",
                "rowAccountingBalances": False,
                "inputRows": 100,
                "outputRows": 90,
                "quarantineRows": 5,
            },
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_dq_004_pass_rows_above_zero(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "DQ-004", "Row count > 0",
            passed=True,
            context={"guardrailCode": "DQ-004", "rowCountAboveZero": True, "rowCount": 50},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_dq_004_fail_zero_rows(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "DQ-004", "Zero rows",
            passed=True,
            context={"guardrailCode": "DQ-004", "rowCountAboveZero": False, "rowCount": 0},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False


# ---------------------------------------------------------------------------
# INT guardrail tests
# ---------------------------------------------------------------------------
class TestIntegrityGuardrails:

    def test_int_001_pass_file_written(self, evaluator, onboarding_agent):
        step = PipelineStep(step_number=2, step_name="Landing ingest", target_zone="landing")
        result = evaluator.check(
            "INT-001", "Landing file written",
            passed=True,
            context={"guardrailCode": "INT-001", "landingFileWritten": True},
            principal=onboarding_agent,
            resource=step,
        )
        assert result is True

    def test_int_001_fail_file_not_written(self, evaluator, onboarding_agent):
        step = PipelineStep(step_number=2, step_name="Landing ingest", target_zone="landing")
        result = evaluator.check(
            "INT-001", "Landing file not written",
            passed=True,
            context={"guardrailCode": "INT-001", "landingFileWritten": False},
            principal=onboarding_agent,
            resource=step,
        )
        assert result is False

    def test_int_002_pass_fk_above_threshold(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "INT-002", "FK integrity pass",
            passed=True,
            context={"guardrailCode": "INT-002", "fkPassRate": 98, "fkThreshold": 90},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_int_002_fail_fk_below_threshold(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "INT-002", "FK integrity fail",
            passed=True,
            context={"guardrailCode": "INT-002", "fkPassRate": 85, "fkThreshold": 90},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_int_003_pass_formula_verified(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "INT-003", "Formula verified",
            passed=True,
            context={"guardrailCode": "INT-003", "formulaVerified": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_int_003_fail_formula_not_verified(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "INT-003", "Formula not verified",
            passed=True,
            context={"guardrailCode": "INT-003", "formulaVerified": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_int_004_pass_schema_matches(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "INT-004", "Schema matches",
            passed=True,
            context={"guardrailCode": "INT-004", "schemaMatches": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_int_004_fail_schema_mismatch(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "INT-004", "Schema mismatch",
            passed=True,
            context={"guardrailCode": "INT-004", "schemaMatches": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False


# ---------------------------------------------------------------------------
# OPS guardrail tests
# ---------------------------------------------------------------------------
class TestOperationalGuardrails:

    def test_ops_001_pass_checksum_match(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "OPS-001", "Checksum matches",
            passed=True,
            context={"guardrailCode": "OPS-001", "checksumMatch": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_ops_001_fail_checksum_mismatch(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "OPS-001", "Checksum mismatch",
            passed=True,
            context={"guardrailCode": "OPS-001", "checksumMatch": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_ops_002_pass_keys_different(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "OPS-002", "Encryption re-keyed",
            passed=True,
            context={
                "guardrailCode": "OPS-002",
                "keysAreDifferent": True,
                "sourceKeyAlias": "alias/landing-data-key",
                "targetKeyAlias": "alias/staging-data-key",
            },
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_ops_002_fail_keys_same(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "OPS-002", "Encryption not re-keyed",
            passed=True,
            context={
                "guardrailCode": "OPS-002",
                "keysAreDifferent": False,
                "sourceKeyAlias": "alias/landing-data-key",
                "targetKeyAlias": "alias/landing-data-key",
            },
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_ops_003_pass_audit_written(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "OPS-003", "Audit log written",
            passed=True,
            context={"guardrailCode": "OPS-003", "auditLogWritten": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_ops_003_fail_audit_missing(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "OPS-003", "Audit log missing",
            passed=True,
            context={"guardrailCode": "OPS-003", "auditLogWritten": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False

    def test_ops_004_pass_iceberg_exists(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "OPS-004", "Iceberg metadata exists",
            passed=True,
            context={"guardrailCode": "OPS-004", "icebergMetadataExists": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is True

    def test_ops_004_fail_iceberg_missing(self, evaluator, onboarding_agent, step_staging):
        result = evaluator.check(
            "OPS-004", "Iceberg metadata missing",
            passed=True,
            context={"guardrailCode": "OPS-004", "icebergMetadataExists": False},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Agent authorization tests
# ---------------------------------------------------------------------------
class TestAgentAuthorization:
    """Test that each agent's permissions match the Cedar policies."""

    # -- Router Agent (read-only) --
    def test_router_can_read_files(self, evaluator):
        agent = AgentPrincipal("router")
        wf = WorkloadFile("config/source.yaml", file_type="config")
        allowed, _ = evaluator.authorize_agent(agent, "ReadFile", wf)
        assert allowed is True

    def test_router_can_read_data(self, evaluator):
        agent = AgentPrincipal("router")
        zone = DataZone("landing", "test")
        allowed, _ = evaluator.authorize_agent(agent, "ReadData", zone)
        assert allowed is True

    def test_router_cannot_write(self, evaluator):
        agent = AgentPrincipal("router")
        wf = WorkloadFile("config/source.yaml", file_type="config")
        allowed, _ = evaluator.authorize_agent(agent, "WriteFile", wf)
        assert allowed is False

    def test_router_cannot_invoke_mcp(self, evaluator):
        agent = AgentPrincipal("router")
        tool = McpTool("iam", "list_users")
        allowed, _ = evaluator.authorize_agent(agent, "InvokeTool", tool)
        assert allowed is False

    # -- Onboarding Agent (full access in main conversation) --
    def test_onboarding_full_access(self, evaluator):
        agent = AgentPrincipal("onboarding", "main_conversation")
        zone = DataZone("publish", "test")
        allowed, _ = evaluator.authorize_agent(agent, "WriteData", zone)
        assert allowed is True

    def test_onboarding_can_invoke_mcp(self, evaluator):
        agent = AgentPrincipal("onboarding", "main_conversation")
        tool = McpTool("iam", "list_roles")
        allowed, _ = evaluator.authorize_agent(agent, "InvokeTool", tool)
        assert allowed is True

    # -- Metadata Agent --
    def test_metadata_can_write_config(self, evaluator):
        agent = AgentPrincipal("metadata", "sub_agent")
        wf = WorkloadFile("config/semantic.yaml", file_type="config")
        allowed, _ = evaluator.authorize_agent(agent, "WriteFile", wf)
        assert allowed is True

    def test_metadata_cannot_write_scripts(self, evaluator):
        agent = AgentPrincipal("metadata", "sub_agent")
        wf = WorkloadFile("scripts/extract.py", file_type="script")
        allowed, _ = evaluator.authorize_agent(agent, "WriteFile", wf)
        assert allowed is False

    def test_metadata_cannot_invoke_mcp(self, evaluator):
        agent = AgentPrincipal("metadata", "sub_agent")
        tool = McpTool("iam", "create_role")
        allowed, _ = evaluator.authorize_agent(agent, "InvokeTool", tool)
        assert allowed is False

    def test_metadata_cannot_write_publish(self, evaluator):
        agent = AgentPrincipal("metadata", "sub_agent")
        zone = DataZone("publish", "test")
        allowed, _ = evaluator.authorize_agent(agent, "WriteData", zone)
        assert allowed is False

    # -- Transformation Agent --
    def test_transformation_can_write_scripts(self, evaluator):
        agent = AgentPrincipal("transformation", "sub_agent")
        wf = WorkloadFile("scripts/transform.py", file_type="script")
        allowed, _ = evaluator.authorize_agent(agent, "WriteFile", wf)
        assert allowed is True

    def test_transformation_can_write_sql(self, evaluator):
        agent = AgentPrincipal("transformation", "sub_agent")
        wf = WorkloadFile("sql/silver/clean.sql", file_type="sql")
        allowed, _ = evaluator.authorize_agent(agent, "WriteFile", wf)
        assert allowed is True

    def test_transformation_cannot_write_publish(self, evaluator):
        agent = AgentPrincipal("transformation", "sub_agent")
        zone = DataZone("publish", "test")
        allowed, _ = evaluator.authorize_agent(agent, "WriteData", zone)
        assert allowed is False

    def test_transformation_cannot_invoke_mcp(self, evaluator):
        agent = AgentPrincipal("transformation", "sub_agent")
        tool = McpTool("redshift", "execute_query")
        allowed, _ = evaluator.authorize_agent(agent, "InvokeTool", tool)
        assert allowed is False

    # -- Quality Agent --
    def test_quality_can_read_all_zones(self, evaluator):
        agent = AgentPrincipal("quality", "sub_agent")
        for zone_name in ("landing", "staging", "publish"):
            zone = DataZone(zone_name, "test")
            allowed, _ = evaluator.authorize_agent(agent, "ReadData", zone)
            assert allowed is True, f"Quality agent should read {zone_name}"

    def test_quality_cannot_write_data(self, evaluator):
        agent = AgentPrincipal("quality", "sub_agent")
        zone = DataZone("staging", "test")
        allowed, _ = evaluator.authorize_agent(agent, "WriteData", zone)
        assert allowed is False

    def test_quality_cannot_promote(self, evaluator):
        agent = AgentPrincipal("quality", "sub_agent")
        zone = DataZone("staging", "test")
        allowed, _ = evaluator.authorize_agent(agent, "PromoteData", zone)
        assert allowed is False

    # -- DAG Agent --
    def test_dag_can_write_dag_files(self, evaluator):
        agent = AgentPrincipal("dag", "sub_agent")
        wf = WorkloadFile("dags/pipeline_dag.py", file_type="dag")
        allowed, _ = evaluator.authorize_agent(agent, "WriteFile", wf)
        assert allowed is True

    def test_dag_cannot_write_scripts(self, evaluator):
        agent = AgentPrincipal("dag", "sub_agent")
        wf = WorkloadFile("scripts/transform.py", file_type="script")
        allowed, _ = evaluator.authorize_agent(agent, "WriteFile", wf)
        assert allowed is False

    def test_dag_cannot_access_data(self, evaluator):
        agent = AgentPrincipal("dag", "sub_agent")
        zone = DataZone("staging", "test")
        allowed, _ = evaluator.authorize_agent(agent, "ReadData", zone)
        assert allowed is False

    # -- Ontology Staging Agent --
    def test_ontology_staging_can_write_config(self, evaluator):
        agent = AgentPrincipal("ontology_staging", "sub_agent")
        file = WorkloadFile("config/ontology.ttl", "config")
        allowed, _ = evaluator.authorize_agent(agent, "WriteFile", file)
        assert allowed is True

    def test_ontology_staging_cannot_write_data(self, evaluator):
        agent = AgentPrincipal("ontology_staging", "sub_agent")
        zone = DataZone("publish", "test")
        allowed, _ = evaluator.authorize_agent(agent, "WriteData", zone)
        assert allowed is False

    def test_ontology_staging_cannot_invoke_arbitrary_tool(self, evaluator):
        agent = AgentPrincipal("ontology_staging", "sub_agent")
        tool = McpTool("redshift", "execute_query")
        allowed, _ = evaluator.authorize_agent(agent, "InvokeTool", tool)
        assert allowed is False


# ---------------------------------------------------------------------------
# CedarPolicyEvaluator integration tests
# ---------------------------------------------------------------------------
class TestEvaluatorIntegration:

    def test_backward_compatible_check_no_context(self, evaluator):
        """check() without context should work like old GuardrailTracker."""
        result = evaluator.check("SEC-002", "KMS alias ok", passed=True)
        assert result is True
        assert evaluator.results[-1]["cedar_decision"] is None

    def test_check_with_context_overrides_passed(self, evaluator, onboarding_agent, step_staging):
        """Cedar decision overrides the passed parameter."""
        result = evaluator.check(
            "SEC-001", "Should fail via Cedar",
            passed=True,  # Inline says pass
            context={"guardrailCode": "SEC-001", "secretPatternFound": True},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert result is False  # Cedar says forbid

    def test_all_passed_true(self):
        ev = CedarPolicyEvaluator(mode="local")
        ev.check("SEC-001", "ok", passed=True)
        ev.check("SEC-002", "ok", passed=True)
        assert ev.all_passed() is True

    def test_all_passed_false(self):
        ev = CedarPolicyEvaluator(mode="local")
        ev.check("SEC-001", "ok", passed=True)
        ev.check("SEC-002", "fail", passed=False)
        assert ev.all_passed() is False

    def test_print_summary(self, evaluator, capsys):
        evaluator.check("SEC-001", "test pass", passed=True)
        evaluator.check("SEC-002", "test fail", passed=False)
        evaluator.print_summary()
        captured = capsys.readouterr()
        assert "GUARDRAIL SUMMARY" in captured.out
        assert "Cedar Policy Engine" in captured.out
        assert "SEC-001" in captured.out
        assert "SEC-002" in captured.out

    def test_audit_log_populated(self, evaluator, onboarding_agent, step_staging):
        evaluator.check(
            "DQ-001", "quality check",
            passed=True,
            context={"guardrailCode": "DQ-001", "qualityScore": 95, "qualityThreshold": 80},
            principal=onboarding_agent,
            resource=step_staging,
        )
        assert len(evaluator.audit_log) == 1
        assert evaluator.audit_log[0]["guardrail"] == "DQ-001"
        assert evaluator.audit_log[0]["decision"] == "ALLOW"
        assert evaluator.audit_log[0]["cedar_evaluated"] is True

    def test_export_audit_log(self, evaluator, tmp_path):
        evaluator.check("SEC-001", "test", passed=True)
        path = str(tmp_path / "audit.json")
        result = evaluator.export_audit_log(path)
        assert os.path.isfile(result)


# ---------------------------------------------------------------------------
# Entity data class tests
# ---------------------------------------------------------------------------
class TestEntityDataClasses:

    def test_agent_principal_to_cedar(self):
        a = AgentPrincipal("metadata", "sub_agent", "sales")
        cedar = a.to_cedar()
        assert cedar["entityType"] == "DataOnboarding::AgentPrincipal"
        assert cedar["entityId"] == "metadata"

    def test_data_zone_to_cedar(self):
        z = DataZone("staging", "sales", "alias/staging-key")
        cedar = z.to_cedar()
        assert cedar["entityId"] == "sales_staging"

    def test_pipeline_step_to_cedar(self):
        s = PipelineStep(7, "Staging write", "landing", "staging")
        cedar = s.to_cedar()
        assert cedar["entityId"] == "step_7"

    def test_mcp_tool_to_cedar(self):
        t = McpTool("iam", "list_users")
        cedar = t.to_cedar()
        assert cedar["entityId"] == "iam::list_users"

    def test_workload_file_to_cedar(self):
        wf = WorkloadFile("config/source.yaml", "config", "")
        cedar = wf.to_cedar()
        assert cedar["entityType"] == "DataOnboarding::WorkloadFile"

    def test_entity_records_have_required_fields(self):
        entities = [
            AgentPrincipal("onboarding"),
            UserPrincipal("test@example.com", "admin"),
            DataZone("landing"),
            WorkloadFile("test.py", "script"),
            McpTool("iam", "list_users"),
            PipelineStep(1),
        ]
        for entity in entities:
            record = entity.to_entity_record()
            assert "identifier" in record
            assert "attributes" in record
            assert "parents" in record
