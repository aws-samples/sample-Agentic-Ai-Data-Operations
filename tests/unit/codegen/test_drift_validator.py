"""Unit tests for shared.codegen.drift_validator."""

from pathlib import Path

import pytest

from shared.codegen.drift_validator import parse_artifact_header, verify_artifact, verify_workload
from shared.codegen.renderer import render
from shared.codegen.spec_loader import load_spec

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "replay_workload" / "config"
RUN_STARTED_AT = "2026-05-21T10:00:00Z"


@pytest.fixture
def rendered_artifact(tmp_path):
    spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")
    output = tmp_path / "workload" / "scripts" / "transform" / "silver.py"
    output.parent.mkdir(parents=True)
    # Also create config dir for drift validator to find
    config_dir = tmp_path / "workload" / "config"
    config_dir.mkdir(parents=True)
    import shutil
    shutil.copy(FIXTURES / "silver.yaml", config_dir / "silver.yaml")
    render(spec, spec_hash, "silver_transform", "1.0.0", output, RUN_STARTED_AT)
    return output


class TestDriftValidator:
    def test_verify_clean_artifact_returns_ok_true(self, rendered_artifact):
        report = verify_artifact(rendered_artifact)
        assert report.ok is True

    def test_verify_hand_edited_artifact_returns_ok_false_with_diff(self, rendered_artifact):
        content = rendered_artifact.read_text()
        rendered_artifact.write_text(content + "\n# hand edit")
        report = verify_artifact(rendered_artifact)
        assert report.ok is False
        assert report.diff is not None or report.reason is not None

    def test_verify_artifact_missing_header_returns_ok_false(self, tmp_path):
        no_header = tmp_path / "workload" / "scripts" / "bad.py"
        no_header.parent.mkdir(parents=True)
        no_header.write_text("print('no header')\n")
        report = verify_artifact(no_header)
        assert report.ok is False
        assert "header" in (report.reason or "").lower()

    def test_verify_artifact_with_tampered_spec_hash_header_returns_ok_false(self, rendered_artifact):
        content = rendered_artifact.read_text()
        lines = content.splitlines()
        lines[0] = "# spec_hash: " + "0" * 64
        rendered_artifact.write_text("\n".join(lines) + "\n")
        report = verify_artifact(rendered_artifact)
        assert report.ok is False

    def test_verify_workload_runs_on_every_generated_file(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        scripts_dir = tmp_path / "scripts" / "transform"
        scripts_dir.mkdir(parents=True)

        import shutil
        shutil.copy(FIXTURES / "silver.yaml", config_dir / "silver.yaml")

        spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")
        out1 = scripts_dir / "file1.py"
        out2 = scripts_dir / "file2.py"
        render(spec, spec_hash, "silver_transform", "1.0.0", out1, RUN_STARTED_AT)
        render(spec, spec_hash, "silver_transform", "1.0.0", out2, RUN_STARTED_AT)

        report = verify_workload(tmp_path)
        assert len(report.reports) == 2
        assert all(r.ok for r in report.reports)

    def test_verify_artifact_with_template_version_mismatch_reports_drift(self, rendered_artifact):
        content = rendered_artifact.read_text()
        content = content.replace("# template_hash:", "# template_hash: 0000000000000000\n# OLD template_hash:")
        rendered_artifact.write_text(content)
        report = verify_artifact(rendered_artifact)
        assert report.ok is False


class TestParseHeader:
    def test_parses_valid_python_header(self):
        content = (
            "# spec_hash: " + "a" * 64 + "\n"
            "# template_id: silver_transform\n"
            "# template_hash: " + "b" * 64 + "\n"
            "# schema_version: v1\n"
            "# rendered_at: 2026-05-21T10:00:00Z\n"
            "import sys\n"
        )
        header = parse_artifact_header(content)
        assert header is not None
        assert header["spec_hash"] == "a" * 64
        assert header["template_id"] == "silver_transform"
        assert header["schema_version"] == "v1"

    def test_returns_none_for_missing_header(self):
        assert parse_artifact_header("import sys\n") is None
