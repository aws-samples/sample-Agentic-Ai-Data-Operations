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

    def _workload(self, tmp_path, rendered=2, handwritten=0):
        """A workload dir with `rendered` headed artifacts and `handwritten` headerless ones."""
        import shutil

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        scripts_dir = tmp_path / "scripts" / "transform"
        scripts_dir.mkdir(parents=True)
        shutil.copy(FIXTURES / "silver.yaml", config_dir / "silver.yaml")
        spec, spec_hash = load_spec(FIXTURES / "silver.yaml", "silver")
        for i in range(rendered):
            render(spec, spec_hash, "silver_transform", "1.0.0",
                   scripts_dir / f"file{i}.py", RUN_STARTED_AT)
        for i in range(handwritten):
            (scripts_dir / f"hand{i}.py").write_text("print('free-form PySpark')\n")
        return tmp_path

    def test_verify_workload_runs_on_every_generated_file(self, tmp_path):
        report = verify_workload(self._workload(tmp_path, rendered=2))
        assert len(report.reports) == 2
        assert all(r.ok for r in report.reports)

    def test_a_headerless_artifact_is_reported_not_skipped(self, tmp_path):
        """This is what the test above did NOT cover, and the gap was not theoretical.

        It rendered two headed files and asserted two reports. Adding a headerless third left
        the count at two and the suite green, because verify_workload appended a report only
        `if parse_artifact_header(content) is not None` — so the directory entry point, which
        is what CI and the orchestrator call, skipped exactly the files that violate
        CLAUDE.md:137. verify_artifact on the same file has always returned ok=False.

        Measured on the real tree at the time: workloads/claims is a complete hand-written
        Bronze->Silver->Gold pipeline plus DAG, and verify_workload reported it clean.
        """
        report = verify_workload(self._workload(tmp_path, rendered=1, handwritten=1))
        assert len(report.reports) == 2, (
            "the hand-written artifact was skipped, so it is indistinguishable from a "
            "rendered one"
        )
        assert report.ok is False
        bad = [r for r in report.reports if not r.ok]
        assert len(bad) == 1 and "header" in (bad[0].reason or "").lower()

    def test_a_workload_of_only_handwritten_files_does_not_pass(self, tmp_path):
        """`ok` is all() over the reports, and all([]) is True.

        So "checked every artifact and found no drift" and "found no artifact to check" were
        the same boolean. files_scanned exists to tell them apart.
        """
        report = verify_workload(self._workload(tmp_path, rendered=0, handwritten=3))
        assert report.ok is False
        assert report.files_scanned == 3

    def test_an_empty_workload_is_distinguishable_from_a_clean_one(self, tmp_path):
        (tmp_path / "config").mkdir()
        report = verify_workload(tmp_path)
        assert report.ok is True, "nothing is wrong with a workload that has no artifacts yet"
        assert report.files_scanned == 0, (
            "ok=True must be accompanied by a count, or a caller cannot tell a clean "
            "workload from an unscanned one"
        )

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


class TestHeaderlessExemptionsAreARatchet:
    """The exemption list is the part most likely to rot into a permission slip.

    Same discipline as KNOWN_UNREAD in test_template_schema_agreement.py: every entry names a
    file that exists, states a reason, and disappears the moment the file is rendered. A stale
    entry is worse than a redundant one — it is a standing exemption, so re-introducing the
    gap later would not fail.
    """

    def _exempt(self):
        from shared.codegen.drift_validator import EXEMPT_HEADERLESS

        return EXEMPT_HEADERLESS

    def test_every_exempt_path_exists(self):
        """A typo is an exemption that protects nothing and hides nothing."""
        root = Path(__file__).resolve().parents[3]
        missing = sorted(k for k in self._exempt() if not (root / k).exists())
        assert not missing, (
            "EXEMPT_HEADERLESS names files that do not exist — delete them:\n  "
            + "\n  ".join(missing)
        )

    def test_no_exempt_file_has_since_been_rendered(self):
        """Once a file carries a header its entry is stale. Deleting it is the point."""
        from shared.codegen.drift_validator import parse_artifact_header

        root = Path(__file__).resolve().parents[3]
        stale = sorted(
            k for k in self._exempt()
            if (root / k).exists()
            and parse_artifact_header((root / k).read_text(errors="ignore")) is not None
        )
        assert not stale, (
            "these now have a provenance header — remove them from EXEMPT_HEADERLESS:\n  "
            + "\n  ".join(stale)
        )

    def test_every_exemption_states_a_reason(self):
        """An undocumented exemption is indistinguishable from an oversight."""
        thin = sorted(k for k, v in self._exempt().items() if len(v.strip()) < 40)
        assert not thin, "exemptions with no usable reason:\n  " + "\n  ".join(thin)

    def test_exemptions_are_exact_paths_not_globs(self):
        """A glob would exempt a file nobody has reviewed.

        `*/scripts/quality/glue_data_quality.py` would cover a third workload's copy the
        moment someone hand-wrote one — the opposite of a ratchet.
        """
        globbed = sorted(k for k in self._exempt() if any(c in k for c in "*?["))
        assert not globbed, "glob patterns in EXEMPT_HEADERLESS:\n  " + "\n  ".join(globbed)

    def test_the_list_only_shrinks(self):
        """A ceiling, so adding an exemption is a deliberate act with a visible diff.

        Set to the six found when verify_workload was fixed. Lower it when one is rendered;
        never raise it — render the artifact instead.
        """
        assert len(self._exempt()) <= 6, (
            f"EXEMPT_HEADERLESS has grown to {len(self._exempt())}. A new hand-written "
            f"artifact should be rendered, not exempted."
        )
