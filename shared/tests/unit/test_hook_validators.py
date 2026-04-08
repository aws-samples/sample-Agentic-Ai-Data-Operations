"""Tests for pre-commit hook validators.

Tests each custom hook module with known-good and known-bad inputs.
"""

import os
import tempfile
from pathlib import Path

import pytest

from shared.utils.hook_validators import pii_code_scanner
from shared.utils.hook_validators import cedar_validator
from shared.utils.hook_validators import yaml_config_validator
from shared.utils.hook_validators import sensitive_info_scanner


# ── PII Code Scanner Tests ─────────────────────────────────────────────


class TestPiiCodeScanner:
    """Tests for pii_code_scanner module."""

    def test_detects_ssn_in_code(self, tmp_path):
        """CRITICAL: SSN pattern in code must be detected."""
        f = tmp_path / "bad_code.py"
        f.write_text('ssn = "123-45-6789"\nprint(ssn)\n')
        findings = pii_code_scanner.scan_file(str(f), [])
        assert len(findings) > 0
        assert any(f["type"] == "SSN" for f in findings)
        assert any(f["sensitivity"] == "CRITICAL" for f in findings)

    def test_detects_credit_card_in_code(self, tmp_path):
        """CRITICAL: Credit card number must be detected."""
        f = tmp_path / "payment.py"
        f.write_text('card = "4111-1111-1111-1111"\n')
        findings = pii_code_scanner.scan_file(str(f), [])
        assert len(findings) > 0
        assert any(f["type"] == "CREDIT_CARD" for f in findings)

    def test_detects_email_in_code(self, tmp_path):
        """HIGH: Email address should be detected."""
        f = tmp_path / "user.py"
        f.write_text('contact = "john.doe@company.com"\n')
        findings = pii_code_scanner.scan_file(str(f), [])
        assert len(findings) > 0
        assert any(f["type"] == "EMAIL" for f in findings)

    def test_ignores_regex_definitions(self, tmp_path):
        """Regex pattern definitions should not trigger PII detection."""
        f = tmp_path / "patterns.py"
        f.write_text(
            "PII_PATTERNS = {\n"
            "    'regex': r'\\b\\d{3}-\\d{2}-\\d{4}\\b',\n"
            "    'description': 'SSN pattern for detection',\n"
            "}\n"
        )
        findings = pii_code_scanner.scan_file(str(f), [])
        assert len(findings) == 0

    def test_ignores_comments(self, tmp_path):
        """Comments describing PII should not trigger detection."""
        f = tmp_path / "documented.py"
        f.write_text("# Example SSN format: 123-45-6789\n")
        findings = pii_code_scanner.scan_file(str(f), [])
        assert len(findings) == 0

    def test_respects_allowed_patterns(self, tmp_path):
        """Patterns in .gitallowed should be skipped."""
        f = tmp_path / "test_data.py"
        f.write_text('test_ssn = "123-45-6789"\n')
        findings = pii_code_scanner.scan_file(str(f), ["123-45-6789"])
        assert len(findings) == 0

    def test_clean_file_returns_empty(self, tmp_path):
        """File without PII should return no findings."""
        f = tmp_path / "clean.py"
        f.write_text(
            "def calculate_total(items):\n"
            "    return sum(item.price for item in items)\n"
        )
        findings = pii_code_scanner.scan_file(str(f), [])
        assert len(findings) == 0

    def test_nonexistent_file_returns_empty(self):
        """Missing file should return empty findings, not crash."""
        findings = pii_code_scanner.scan_file("/nonexistent/file.py", [])
        assert len(findings) == 0

    def test_false_positive_check(self):
        """Verify false positive detection logic."""
        assert pii_code_scanner.is_false_positive("# comment about emails")
        assert pii_code_scanner.is_false_positive("regex = r'\\b...'")
        assert pii_code_scanner.is_false_positive("PII_PATTERNS = {")
        assert not pii_code_scanner.is_false_positive('value = "real@email.com"')


# ── Cedar Validator Tests ──────────────────────────────────────────────


class TestCedarValidator:
    """Tests for cedar_validator module."""

    def test_valid_forbid_policy(self, tmp_path):
        """Valid forbid policy should pass."""
        f = tmp_path / "valid.cedar"
        f.write_text(
            'forbid (principal, action == Action::"PassSecurityCheck", resource)\n'
            "when {\n"
            '    context.guardrailCode == "SEC-001" &&\n'
            "    context.secretPatternFound == true\n"
            "};\n"
        )
        errors = cedar_validator.validate_file(str(f))
        assert len(errors) == 0

    def test_valid_permit_policy(self, tmp_path):
        """Valid permit policy should pass."""
        f = tmp_path / "permit.cedar"
        f.write_text(
            "permit (\n"
            "    principal == AgentPrincipal::\"router\",\n"
            '    action == Action::"ReadFile",\n'
            "    resource\n"
            ");\n"
        )
        errors = cedar_validator.validate_file(str(f))
        assert len(errors) == 0

    def test_missing_forbid_permit(self, tmp_path):
        """Policy without forbid/permit should fail."""
        f = tmp_path / "bad.cedar"
        f.write_text("when { context.something == true };\n")
        errors = cedar_validator.validate_file(str(f))
        assert len(errors) > 0
        assert any("forbid" in e or "permit" in e for e in errors)

    def test_unbalanced_braces(self, tmp_path):
        """Unbalanced braces should fail."""
        f = tmp_path / "unbalanced.cedar"
        f.write_text(
            "forbid (principal, action, resource)\n"
            "when {\n"
            "    context.foo == true\n"
            ";\n"
        )
        errors = cedar_validator.validate_file(str(f))
        assert len(errors) > 0
        assert any("brace" in e for e in errors)

    def test_empty_file_fails(self, tmp_path):
        """Empty Cedar file should fail."""
        f = tmp_path / "empty.cedar"
        f.write_text("")
        errors = cedar_validator.validate_file(str(f))
        assert len(errors) > 0

    def test_schema_file_valid(self, tmp_path):
        """Valid schema file should pass."""
        f = tmp_path / "test.cedarschema"
        f.write_text(
            "entity AgentPrincipal {\n"
            "    agent_type: String,\n"
            "};\n"
            'action ReadData appliesTo {\n'
            "    principal: [AgentPrincipal],\n"
            "    resource: [DataZone]\n"
            "};\n"
        )
        errors = cedar_validator.validate_file(str(f))
        assert len(errors) == 0

    def test_schema_file_missing_definitions(self, tmp_path):
        """Schema without entity/action definitions should fail."""
        f = tmp_path / "bad.cedarschema"
        f.write_text("// just a comment, no definitions\n")
        errors = cedar_validator.validate_file(str(f))
        assert len(errors) > 0

    def test_nonexistent_file_returns_error(self):
        """Missing file should return an error."""
        errors = cedar_validator.validate_file("/nonexistent/policy.cedar")
        assert len(errors) > 0

    def test_real_guardrail_files_pass(self):
        """All existing guardrail policies should pass validation."""
        guardrails_dir = cedar_validator.POLICIES_DIR / "guardrails"
        if not guardrails_dir.exists():
            pytest.skip("Guardrails directory not found")
        for policy_file in guardrails_dir.glob("*.cedar"):
            errors = cedar_validator.validate_file(str(policy_file))
            assert len(errors) == 0, f"{policy_file.name} failed: {errors}"

    def test_real_agent_auth_files_pass(self):
        """All existing agent authorization policies should pass validation."""
        auth_dir = cedar_validator.POLICIES_DIR / "agent_authorization"
        if not auth_dir.exists():
            pytest.skip("Agent authorization directory not found")
        for policy_file in auth_dir.glob("*.cedar"):
            errors = cedar_validator.validate_file(str(policy_file))
            assert len(errors) == 0, f"{policy_file.name} failed: {errors}"


# ── YAML Config Validator Tests ────────────────────────────────────────


class TestYamlConfigValidator:
    """Tests for yaml_config_validator module."""

    def test_valid_source_yaml(self, tmp_path):
        """Valid source.yaml should pass."""
        f = tmp_path / "source.yaml"
        f.write_text(
            "source_type: postgresql\n"
            "location: ${AIRFLOW_CONN_POSTGRES}\n"
            "format: csv\n"
        )
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) == 0

    def test_valid_source_yaml_nested(self, tmp_path):
        """source.yaml with nested 'source' key should pass."""
        f = tmp_path / "source.yaml"
        f.write_text(
            "source:\n"
            "  name: test_workload\n"
            "  type: s3\n"
        )
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) == 0

    def test_valid_quality_rules_yaml(self, tmp_path):
        """Valid quality_rules.yaml should pass."""
        f = tmp_path / "quality_rules.yaml"
        f.write_text(
            "silver_rules:\n"
            "  test_table:\n"
            "    completeness:\n"
            "      - column: id\n"
        )
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) == 0

    def test_valid_schedule_yaml(self, tmp_path):
        """Valid schedule.yaml should pass."""
        f = tmp_path / "schedule.yaml"
        f.write_text(
            "schedule:\n"
            "  frequency: daily\n"
            "  cron_expression: '0 6 * * *'\n"
        )
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) == 0

    def test_valid_semantic_yaml(self, tmp_path):
        """Valid semantic.yaml should pass."""
        f = tmp_path / "semantic.yaml"
        f.write_text(
            "tables:\n"
            "  silver:\n"
            "    test_table:\n"
            "      primary_key: id\n"
        )
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) == 0

    def test_detects_hardcoded_password_in_yaml(self, tmp_path):
        """Hardcoded password in YAML should be flagged."""
        f = tmp_path / "source.yaml"
        f.write_text(
            "source_type: postgresql\n"
            "location: localhost\n"
            "format: csv\n"
            'password: "my_secret_pass123"\n'
        )
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) > 0
        assert any("password" in e.lower() or "secret" in e.lower() for e in errors)

    def test_invalid_yaml_syntax(self, tmp_path):
        """Invalid YAML should be caught."""
        f = tmp_path / "broken.yaml"
        f.write_text("key: [unclosed bracket\n")
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) > 0
        assert any("parse error" in e.lower() or "YAML" in e for e in errors)

    def test_empty_yaml_fails(self, tmp_path):
        """Empty YAML file should fail."""
        f = tmp_path / "source.yaml"
        f.write_text("")
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) > 0

    def test_unknown_config_type_still_scans_secrets(self, tmp_path):
        """Unknown config types should still get secret scanning."""
        f = tmp_path / "custom_config.yaml"
        f.write_text(
            'db_password: "SuperSecret123!"\n'
            "some_key: some_value\n"
        )
        errors = yaml_config_validator.validate_file(str(f))
        assert len(errors) > 0


# ── Sensitive Info Scanner Tests ───────────────────────────────────────


class TestSensitiveInfoScanner:
    """Tests for sensitive_info_scanner module."""

    def test_detects_hardcoded_password(self, tmp_path):
        """Hardcoded password assignment must be caught."""
        f = tmp_path / "config.py"
        f.write_text('DB_PASSWORD = "SuperSecret123!"\n')
        findings = sensitive_info_scanner.scan_file(str(f), [])
        assert len(findings) > 0
        assert any("Password" in f["name"] or "Token" in f["name"] for f in findings)

    def test_detects_private_key(self, tmp_path):
        """Private key marker must be caught."""
        f = tmp_path / "certs.py"
        # Use a dynamically constructed marker to avoid triggering Code Defender
        marker = "-----BEGIN " + "RSA PRIVATE " + "KEY-----"
        f.write_text(f'key = """{marker}\nMIIE..."""\n')
        findings = sensitive_info_scanner.scan_file(str(f), [])
        assert len(findings) > 0
        assert any("Private Key" in f["name"] for f in findings)

    def test_detects_connection_string_with_creds(self, tmp_path):
        """Connection string with embedded credentials must be caught."""
        f = tmp_path / "db.py"
        f.write_text('conn = "postgresql://admin:secret@db.example.com:5432/mydb"\n')
        findings = sensitive_info_scanner.scan_file(str(f), [])
        assert len(findings) > 0
        assert any("Connection String" in f["name"] for f in findings)

    def test_detects_generic_secret(self, tmp_path):
        """Generic secret assignment must be caught."""
        f = tmp_path / "auth.py"
        f.write_text('SECRET = "aGVsbG8gd29ybGQgdGhpcyBpcyBhIHRlc3Q="\n')
        findings = sensitive_info_scanner.scan_file(str(f), [])
        assert len(findings) > 0

    def test_allows_placeholder_s3_buckets(self, tmp_path):
        """Placeholder S3 bucket names should not be flagged."""
        f = tmp_path / "config.py"
        f.write_text('BUCKET = "s3://your-datalake-bucket/data"\n')
        findings = sensitive_info_scanner.scan_file(str(f), [])
        s3_findings = [f for f in findings if "S3" in f["name"]]
        assert len(s3_findings) == 0

    def test_allows_test_account_id(self, tmp_path):
        """Test account ID (123456789012) should not be flagged."""
        f = tmp_path / "config.py"
        f.write_text('aws_account_id = "123456789012"  # test account\n')
        findings = sensitive_info_scanner.scan_file(
            str(f), sensitive_info_scanner.GLOBAL_ALLOWED
        )
        assert len(findings) == 0

    def test_ignores_regex_definitions(self, tmp_path):
        """Lines defining regex patterns should not trigger detection."""
        f = tmp_path / "scanner.py"
        f.write_text(
            "SENSITIVE_PATTERNS = [\n"
            "    {'regex': r'password\\s*=', 'description': 'password detection'},\n"
            "]\n"
        )
        findings = sensitive_info_scanner.scan_file(str(f), [])
        assert len(findings) == 0

    def test_ignores_comments(self, tmp_path):
        """Comments should not trigger detection."""
        f = tmp_path / "documented.py"
        f.write_text("# password = 'example_password_here'\n")
        findings = sensitive_info_scanner.scan_file(str(f), [])
        assert len(findings) == 0

    def test_clean_file_returns_empty(self, tmp_path):
        """Clean file should return no findings."""
        f = tmp_path / "clean.py"
        f.write_text(
            "import os\n\n"
            "DB_HOST = os.environ.get('DB_HOST', 'localhost')\n"
            "DB_PASSWORD = os.environ['DB_PASSWORD']\n"
        )
        findings = sensitive_info_scanner.scan_file(str(f), [])
        assert len(findings) == 0

    def test_nonexistent_file_returns_empty(self):
        """Missing file should not crash."""
        findings = sensitive_info_scanner.scan_file("/nonexistent/file.py", [])
        assert len(findings) == 0

    def test_false_positive_check(self):
        """Verify false positive detection logic."""
        assert sensitive_info_scanner.is_false_positive("# comment")
        assert sensitive_info_scanner.is_false_positive("regex = r'...'")
        assert sensitive_info_scanner.is_false_positive("SENSITIVE_PATTERNS = [")
        assert not sensitive_info_scanner.is_false_positive('password = "real"')
