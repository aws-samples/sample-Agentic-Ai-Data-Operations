"""Tests for WorkloadMemory — per-workload persistent memory system."""
import pytest
from shared.memory.workload_memory import (
    WorkloadMemory,
    LEDGER_NAME,
    LEDGER_LINE_CAP,
    LEDGER_BYTE_CAP,
    RECOGNIZED_TYPES,
)


@pytest.fixture
def mem(tmp_path):
    """Create a WorkloadMemory rooted in tmp_path."""
    return WorkloadMemory("test_workload", base_dir=tmp_path)


# ---------------------------------------------------------------------------
# TestInit
# ---------------------------------------------------------------------------


class TestInit:
    def test_memory_dir_path(self, tmp_path):
        mem = WorkloadMemory("my_workload", base_dir=tmp_path)
        assert mem.memory_dir == tmp_path / "my_workload" / "memory"

    def test_dir_created_on_first_inscribe(self, mem):
        assert not mem.memory_dir.exists()
        mem.inscribe("test.md", "project", "Test", "A test memory", "body")
        assert mem.memory_dir.exists()
        assert mem.memory_dir.is_dir()


# ---------------------------------------------------------------------------
# TestInscribe
# ---------------------------------------------------------------------------


class TestInscribe:
    def test_correct_frontmatter(self, mem):
        mem.inscribe("note.md", "user", "My Note", "A short desc", "Hello world")
        content = (mem.memory_dir / "note.md").read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "name: My Note\n" in content
        assert "description: A short desc\n" in content
        assert "type: user\n" in content
        assert "---\n\nHello world" in content

    def test_invalid_type_raises(self, mem):
        with pytest.raises(ValueError, match="memory_type must be one of"):
            mem.inscribe("bad.md", "invalid_type", "Bad", "desc", "body")

    def test_content_preserved_exactly(self, mem):
        body = "Line 1\n\n## Section\n- bullet\n- bullet 2\n"
        mem.inscribe("exact.md", "reference", "Exact", "desc", body)
        raw = (mem.memory_dir / "exact.md").read_text(encoding="utf-8")
        # Strip frontmatter and check body
        after_frontmatter = raw.split("---\n\n", 1)[1]
        assert after_frontmatter == body

    def test_description_single_line(self, mem):
        mem.inscribe(
            "multi.md", "feedback", "Multi", "line one\nline two\nline three", "body"
        )
        content = (mem.memory_dir / "multi.md").read_text(encoding="utf-8")
        # Extract description line from frontmatter
        for line in content.splitlines():
            if line.startswith("description:"):
                assert "\n" not in line
                assert "line one line two line three" in line
                break
        else:
            pytest.fail("No description line found in frontmatter")


# ---------------------------------------------------------------------------
# TestReadLedger
# ---------------------------------------------------------------------------


class TestReadLedger:
    def test_returns_empty_when_no_ledger(self, mem):
        assert mem.read_ledger() == ""

    def test_truncates_at_line_cap(self, mem):
        mem._ensure_dir()
        lines = [f"Line {i}\n" for i in range(LEDGER_LINE_CAP + 50)]
        mem.ledger_path.write_text("".join(lines), encoding="utf-8")
        result = mem.read_ledger()
        assert len(result.splitlines()) == LEDGER_LINE_CAP

    def test_truncates_at_byte_cap(self, mem):
        mem._ensure_dir()
        # Create content larger than LEDGER_BYTE_CAP
        big_content = "X" * (LEDGER_BYTE_CAP + 5000)
        mem.ledger_path.write_text(big_content, encoding="utf-8")
        result = mem.read_ledger()
        assert len(result.encode("utf-8")) <= LEDGER_BYTE_CAP

    def test_returns_full_content_under_limits(self, mem):
        mem._ensure_dir()
        small_content = "# Memory: test\n\n- [Note](note.md) — a note\n"
        mem.ledger_path.write_text(small_content, encoding="utf-8")
        assert mem.read_ledger() == small_content


# ---------------------------------------------------------------------------
# TestRebuildLedger
# ---------------------------------------------------------------------------


class TestRebuildLedger:
    def test_contains_all_memory_files(self, mem):
        mem.inscribe("alpha.md", "project", "Alpha", "First file", "body alpha")
        mem.inscribe("beta.md", "user", "Beta", "Second file", "body beta")
        ledger = mem.read_ledger()
        assert "alpha.md" in ledger
        assert "beta.md" in ledger
        assert "Alpha" in ledger
        assert "Beta" in ledger

    def test_format_name_file_desc(self, mem):
        mem.inscribe("info.md", "reference", "Info", "Some info here", "content")
        ledger = mem.read_ledger()
        # Should contain the format: - [name](filename) — description
        assert "- [Info](info.md) \u2014 Some info here" in ledger

    def test_respects_line_cap(self, mem):
        # Create enough files to exceed line cap when each adds a ledger entry
        for i in range(LEDGER_LINE_CAP + 10):
            fname = f"file_{i:04d}.md"
            path = mem.memory_dir / fname
            mem._ensure_dir()
            path.write_text(
                f"---\nname: File {i}\ndescription: desc {i}\ntype: project\n---\n\nbody",
                encoding="utf-8",
            )
        mem.rebuild_ledger()
        ledger = mem.read_ledger()
        assert len(ledger.splitlines()) <= LEDGER_LINE_CAP


# ---------------------------------------------------------------------------
# TestSurvey
# ---------------------------------------------------------------------------


class TestSurvey:
    def test_returns_frontmatter_not_body(self, mem):
        mem.inscribe("secret.md", "project", "Secret", "Short desc", "LONG BODY TEXT HERE")
        results = mem.survey()
        assert len(results) == 1
        entry = results[0]
        assert entry["name"] == "Secret"
        assert entry["description"] == "Short desc"
        assert "LONG BODY TEXT HERE" not in str(entry)

    def test_excludes_memory_md(self, mem):
        mem.inscribe("real.md", "project", "Real", "A real file", "body")
        # MEMORY.md is auto-created by inscribe via rebuild_ledger
        results = mem.survey()
        filenames = [r["filename"] for r in results]
        assert LEDGER_NAME not in filenames
        assert "real.md" in filenames

    def test_includes_mtime(self, mem):
        mem.inscribe("timed.md", "feedback", "Timed", "Has mtime", "body")
        results = mem.survey()
        assert len(results) == 1
        assert "mtime" in results[0]
        # mtime should be an ISO format string
        assert "T" in results[0]["mtime"]


# ---------------------------------------------------------------------------
# TestCompose
# ---------------------------------------------------------------------------


class TestCompose:
    def test_includes_only_selected_files(self, mem):
        mem.inscribe("included.md", "project", "Included", "yes", "INCLUDED BODY")
        mem.inscribe("excluded.md", "project", "Excluded", "no", "EXCLUDED BODY")
        injection = mem.compose_injection(["included.md"])
        assert "INCLUDED BODY" in injection
        assert "EXCLUDED BODY" not in injection

    def test_always_includes_ledger(self, mem):
        mem.inscribe("file.md", "project", "File", "desc", "body")
        injection = mem.compose_injection([])
        # Ledger content (the index) should be present even with no selected files
        assert "# Memory: test_workload" in injection

    def test_has_workload_name_header(self, mem):
        injection = mem.compose_injection([])
        assert "## Memory for test_workload" in injection

    def test_missing_files_silently_skipped(self, mem):
        mem.inscribe("exists.md", "project", "Exists", "desc", "EXISTS BODY")
        # Request a file that does not exist — should not raise
        injection = mem.compose_injection(["exists.md", "ghost.md"])
        assert "EXISTS BODY" in injection
        assert "ghost.md" not in injection
