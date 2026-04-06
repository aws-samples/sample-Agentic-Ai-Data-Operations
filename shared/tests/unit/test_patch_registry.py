"""
Tests for the Adaptive Prompt Registry (PromptEvolver).

Uses tmp_path for all filesystem operations so nothing touches the real repo.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# We need to make sure the shared package is importable
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from shared.prompt_intelligence.patch_registry import (
    PromptEvolver,
    CONFIDENCE_GATE,
    _slugify,
)
from shared.prompt_intelligence.schemas import CrossWorkloadPattern


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINI_SKILLS = """# SKILLS.md

## Phase 1: Discovery

Ask the human questions here.

## Phase 4: Build Pipeline

Spawn sub-agents here.

## Phase 5: Deploy
"""


def _make_pattern(
    signature="KeyError: 'primary_key'",
    agent_type="metadata",
    phase=1,
    confidence=0.85,
    frequency=7,
    prompt_patch="Always ask for PK.",
    prompt_section="Phase 1: Discovery",
    pattern_id=None,
):
    """Helper: build a CrossWorkloadPattern with sensible defaults."""
    if pattern_id is None:
        pattern_id = CrossWorkloadPattern.generate_pattern_id(
            signature, agent_type, phase
        )
    return CrossWorkloadPattern(
        pattern_id=pattern_id,
        pattern_type="schema_error",
        signature=signature,
        frequency=frequency,
        workloads_affected=["wl_a", "wl_b"],
        agent_type=agent_type,
        phase=phase,
        recommendation="Ask for PK",
        confidence=confidence,
        impact="blocking",
        root_cause="Missing PK",
        prompt_section=prompt_section,
        prompt_patch=prompt_patch,
    )


@pytest.fixture
def repo(tmp_path):
    """Set up a minimal repo structure with SKILLS.md and patches dir."""
    (tmp_path / "SKILLS.md").write_text(MINI_SKILLS, encoding="utf-8")
    patches_dir = tmp_path / "shared" / "prompt_intelligence" / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)
    (patches_dir / "PATCH_INDEX.md").write_text(
        "# Prompt Patch Index\nNo patches registered yet.\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def evolver(repo):
    """PromptEvolver pointed at the tmp repo."""
    return PromptEvolver(repo_root=repo)


# ---------------------------------------------------------------------------
# TestHarvestInsights
# ---------------------------------------------------------------------------


class TestHarvestInsights:
    """Tests for harvest_insights()."""

    def test_harvest_creates_patch_file(self, evolver, repo):
        pattern = _make_pattern(confidence=0.70)
        result = evolver.harvest_insights([pattern], auto_graft=False)
        assert result["harvested"] == 1
        assert result["pending"] == 1
        patches = list(evolver.patch_dir.glob("*.patch"))
        assert len(patches) == 1

    def test_harvest_skips_without_prompt_patch(self, evolver):
        pattern = _make_pattern(prompt_patch=None)
        result = evolver.harvest_insights([pattern], auto_graft=False)
        assert result["harvested"] == 0

    def test_harvest_skips_duplicates(self, evolver):
        pattern = _make_pattern(confidence=0.70)
        evolver.harvest_insights([pattern], auto_graft=False)
        result = evolver.harvest_insights([pattern], auto_graft=False)
        assert result["duplicates_skipped"] == 1
        assert result["harvested"] == 0

    def test_harvest_auto_grafts_high_confidence(self, evolver, repo):
        pattern = _make_pattern(confidence=0.90)
        result = evolver.harvest_insights([pattern], auto_graft=True)
        assert result["grafted"] == 1
        assert result["pending"] == 0
        # Verify SKILLS.md was modified
        skills = (repo / "SKILLS.md").read_text()
        assert "<!-- GRAFT:" in skills

    def test_harvest_leaves_low_confidence_as_pending(self, evolver, repo):
        pattern = _make_pattern(confidence=0.60)
        result = evolver.harvest_insights([pattern], auto_graft=True)
        assert result["grafted"] == 0
        assert result["pending"] == 1
        # SKILLS.md unchanged
        skills = (repo / "SKILLS.md").read_text()
        assert "<!-- GRAFT:" not in skills

    def test_harvest_returns_correct_counts(self, evolver):
        patterns = [
            _make_pattern(
                signature="err1", confidence=0.90, prompt_patch="fix1"
            ),
            _make_pattern(
                signature="err2", confidence=0.50, prompt_patch="fix2"
            ),
            _make_pattern(
                signature="err3", confidence=0.70, prompt_patch=None
            ),
        ]
        result = evolver.harvest_insights(patterns, auto_graft=True)
        assert result["harvested"] == 2
        assert result["grafted"] == 1
        assert result["pending"] == 1


# ---------------------------------------------------------------------------
# TestGraftPatch
# ---------------------------------------------------------------------------


class TestGraftPatch:
    """Tests for graft_patch()."""

    def test_graft_appends_to_correct_section(self, evolver, repo):
        pattern = _make_pattern(
            confidence=0.50, prompt_section="Phase 1: Discovery"
        )
        evolver.harvest_insights([pattern], auto_graft=False)
        patches = evolver.census()
        pid = patches[0]["patch_id"]

        evolver.graft_patch(pid, skills_path=repo / "SKILLS.md")

        skills = (repo / "SKILLS.md").read_text()
        # Graft should appear BEFORE "## Phase 4"
        graft_pos = skills.index(f"<!-- GRAFT: {pid}")
        phase4_pos = skills.index("## Phase 4")
        assert graft_pos < phase4_pos

    def test_graft_wrapped_in_markers(self, evolver, repo):
        pattern = _make_pattern(confidence=0.50)
        evolver.harvest_insights([pattern], auto_graft=False)
        pid = evolver.census()[0]["patch_id"]
        evolver.graft_patch(pid, skills_path=repo / "SKILLS.md")

        skills = (repo / "SKILLS.md").read_text()
        assert f"<!-- GRAFT: {pid}" in skills
        assert f"<!-- END GRAFT: {pid} -->" in skills

    def test_graft_is_idempotent(self, evolver, repo):
        pattern = _make_pattern(confidence=0.50)
        evolver.harvest_insights([pattern], auto_graft=False)
        pid = evolver.census()[0]["patch_id"]

        first = evolver.graft_patch(pid, skills_path=repo / "SKILLS.md")
        second = evolver.graft_patch(pid, skills_path=repo / "SKILLS.md")
        assert first is True
        assert second is False

    def test_graft_returns_false_if_section_not_found(self, evolver, repo):
        pattern = _make_pattern(
            confidence=0.50, prompt_section="Phase 99: Nonexistent"
        )
        evolver.harvest_insights([pattern], auto_graft=False)
        pid = evolver.census()[0]["patch_id"]
        result = evolver.graft_patch(pid, skills_path=repo / "SKILLS.md")
        assert result is False

    def test_graft_updates_status(self, evolver, repo):
        pattern = _make_pattern(confidence=0.50)
        evolver.harvest_insights([pattern], auto_graft=False)
        pid = evolver.census()[0]["patch_id"]
        evolver.graft_patch(pid, skills_path=repo / "SKILLS.md")

        updated = evolver.census()
        assert updated[0]["status"] == "applied"
        assert updated[0]["applied_at"] is not None

    def test_graft_updates_index(self, evolver, repo):
        pattern = _make_pattern(confidence=0.50)
        evolver.harvest_insights([pattern], auto_graft=False)
        pid = evolver.census()[0]["patch_id"]
        evolver.graft_patch(pid, skills_path=repo / "SKILLS.md")

        index = (evolver.patch_dir / "PATCH_INDEX.md").read_text()
        assert "applied" in index


# ---------------------------------------------------------------------------
# TestPrunePatch
# ---------------------------------------------------------------------------


class TestPrunePatch:
    """Tests for prune_patch()."""

    def test_prune_removes_block(self, evolver, repo):
        pattern = _make_pattern(confidence=0.90)
        evolver.harvest_insights([pattern], auto_graft=True)
        pid = evolver.census()[0]["patch_id"]

        skills_before = (repo / "SKILLS.md").read_text()
        assert f"<!-- GRAFT: {pid}" in skills_before

        evolver.prune_patch(pid, skills_path=repo / "SKILLS.md")
        skills_after = (repo / "SKILLS.md").read_text()
        assert f"<!-- GRAFT: {pid}" not in skills_after

    def test_prune_resets_status(self, evolver, repo):
        pattern = _make_pattern(confidence=0.90)
        evolver.harvest_insights([pattern], auto_graft=True)
        pid = evolver.census()[0]["patch_id"]
        assert evolver.census()[0]["status"] == "applied"

        evolver.prune_patch(pid, skills_path=repo / "SKILLS.md")
        assert evolver.census()[0]["status"] == "pending"
        assert evolver.census()[0]["applied_at"] is None

    def test_prune_unapplied_returns_false(self, evolver, repo):
        pattern = _make_pattern(confidence=0.50)
        evolver.harvest_insights([pattern], auto_graft=False)
        pid = evolver.census()[0]["patch_id"]
        result = evolver.prune_patch(pid, skills_path=repo / "SKILLS.md")
        assert result is False


# ---------------------------------------------------------------------------
# TestRebuildIndex
# ---------------------------------------------------------------------------


class TestRebuildIndex:
    """Tests for rebuild_index()."""

    def test_index_contains_all_patches(self, evolver, repo):
        patterns = [
            _make_pattern(signature="err1", confidence=0.70, prompt_patch="fix1"),
            _make_pattern(signature="err2", confidence=0.90, prompt_patch="fix2"),
        ]
        evolver.harvest_insights(patterns, auto_graft=False)
        index = (evolver.patch_dir / "PATCH_INDEX.md").read_text()
        assert index.count(".patch") == 2

    def test_index_shows_status(self, evolver, repo):
        pattern = _make_pattern(confidence=0.90)
        evolver.harvest_insights([pattern], auto_graft=True)
        index = (evolver.patch_dir / "PATCH_INDEX.md").read_text()
        assert "applied" in index


# ---------------------------------------------------------------------------
# TestTally
# ---------------------------------------------------------------------------


class TestTally:
    """Tests for tally()."""

    def test_tally_empty(self, evolver):
        t = evolver.tally()
        assert t == {"total": 0, "applied": 0, "pending": 0, "rejected": 0}

    def test_tally_mixed(self, evolver, repo):
        p1 = _make_pattern(signature="e1", confidence=0.90, prompt_patch="f1")
        p2 = _make_pattern(signature="e2", confidence=0.50, prompt_patch="f2")
        evolver.harvest_insights([p1, p2], auto_graft=True)
        t = evolver.tally()
        assert t["total"] == 2
        assert t["applied"] == 1
        assert t["pending"] == 1


# ---------------------------------------------------------------------------
# TestAnalyzeAndEvolve
# ---------------------------------------------------------------------------


class TestAnalyzeAndEvolve:
    """Tests for FailureAnalyzer.analyze_and_evolve()."""

    def test_full_cycle_with_mocked_data(self, evolver, repo):
        from shared.prompt_intelligence.failure_analyzer import FailureAnalyzer
        from shared.prompt_intelligence.schemas import FailurePattern

        analyzer = FailureAnalyzer(workloads_dir=repo / "workloads")

        # Create a workload with trace data
        wl_dir = repo / "workloads" / "test_wl" / "logs"
        wl_dir.mkdir(parents=True)
        events = [
            {
                "status": "failed",
                "error": "KeyError: 'primary_key' in schema inference",
                "agent": "metadata",
                "phase": 1,
                "timestamp": "2026-01-01T00:00:00Z",
                "agent_output": {"decisions": []},
            },
            {
                "status": "failed",
                "error": "KeyError: 'primary_key' in schema inference",
                "agent": "metadata",
                "phase": 1,
                "timestamp": "2026-01-02T00:00:00Z",
                "agent_output": {"decisions": []},
            },
        ]
        trace_path = wl_dir / "trace_events.jsonl"
        trace_path.write_text(
            "\n".join(json.dumps(e) for e in events), encoding="utf-8"
        )

        result = analyzer.analyze_and_evolve(
            prompt_evolver=evolver,
            auto_graft=True,
            min_confidence=0.0,
        )
        assert result["workloads_analyzed"] >= 1
        assert result["patterns_found"] >= 1

    def test_min_confidence_filter(self, evolver, repo):
        from shared.prompt_intelligence.failure_analyzer import FailureAnalyzer

        analyzer = FailureAnalyzer(workloads_dir=repo / "workloads")

        # Create minimal trace
        wl_dir = repo / "workloads" / "low_conf" / "logs"
        wl_dir.mkdir(parents=True)
        event = {
            "status": "failed",
            "error": "KeyError: 'primary_key'",
            "agent": "metadata",
            "phase": 1,
            "timestamp": "2026-01-01T00:00:00Z",
            "agent_output": {"decisions": []},
        }
        (wl_dir / "trace_events.jsonl").write_text(
            json.dumps(event), encoding="utf-8"
        )

        # With very high min_confidence, nothing should be harvested
        result = analyzer.analyze_and_evolve(
            prompt_evolver=evolver,
            auto_graft=False,
            min_confidence=0.99,
        )
        assert result["harvested"] == 0


# ---------------------------------------------------------------------------
# TestSlugify
# ---------------------------------------------------------------------------


class TestSlugify:
    """Tests for the _slugify helper."""

    def test_basic(self):
        assert _slugify("Phase 1: Discovery") == "phase_1_discovery"

    def test_special_chars(self):
        assert _slugify("KeyError: 'primary_key'") == "keyerror_primary_key"
