"""
WorkloadMemory — per-workload persistent memory system.

- MEMORY.md is the ledger (200-line cap, 25KB cap)
- Individual .md files store each memory topic
- Four types: user, feedback, project, reference
- Memory is injected into sub-agent system prompts

Storage: workloads/{workload_name}/memory/
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml


LEDGER_NAME = "MEMORY.md"
LEDGER_LINE_CAP = 200
LEDGER_BYTE_CAP = 25_000
RECOGNIZED_TYPES = frozenset({"user", "feedback", "project", "reference"})

# What NOT to save — keep memory focused on durable, non-obvious facts
EXCLUSION_GUIDANCE = """
Do NOT save:
- Things derivable from config files (schema is in source.yaml, not memory)
- Boilerplate decisions identical across all workloads
- One-time transient errors (network timeout, Glue cold start)
- File contents or code patterns
"""


class WorkloadMemory:
    """Manages persistent memory for a single workload."""

    def __init__(self, workload_name: str, base_dir: Optional[Path] = None):
        """
        Args:
            workload_name: e.g. "financial_portfolios"
            base_dir: Parent directory containing workload dirs.
                      Defaults to <repo_root>/workloads/
        """
        if base_dir is None:
            # Navigate from shared/memory/ up to repo root, then into workloads/
            base_dir = Path(__file__).resolve().parent.parent.parent / "workloads"
        self.workload_name = workload_name
        self.memory_dir = base_dir / workload_name / "memory"

    @property
    def ledger_path(self) -> Path:
        return self.memory_dir / LEDGER_NAME

    def _ensure_dir(self):
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def read_ledger(self) -> str:
        """
        Load MEMORY.md content, truncated to caps.
        Returns empty string if no ledger exists.
        """
        if not self.ledger_path.exists():
            return ""
        content = self.ledger_path.read_text(encoding="utf-8")
        # Truncate at byte cap
        if len(content.encode("utf-8")) > LEDGER_BYTE_CAP:
            content = content.encode("utf-8")[:LEDGER_BYTE_CAP].decode(
                "utf-8", errors="ignore"
            )
        # Truncate at line cap
        lines = content.splitlines(keepends=True)
        if len(lines) > LEDGER_LINE_CAP:
            lines = lines[:LEDGER_LINE_CAP]
            content = "".join(lines)
        return content

    def inscribe(
        self,
        filename: str,
        memory_type: str,
        name: str,
        description: str,
        content: str,
    ) -> Path:
        """
        Write a memory file with frontmatter. Rebuilds ledger after.

        Args:
            filename: e.g. "source_facts.md"
            memory_type: one of RECOGNIZED_TYPES
            name: short title
            description: ONE LINE — retrieval key
            content: body text

        Returns:
            Path to the written file

        Raises:
            ValueError: if memory_type not recognized
        """
        if memory_type not in RECOGNIZED_TYPES:
            raise ValueError(
                f"memory_type must be one of {sorted(RECOGNIZED_TYPES)}, got '{memory_type}'"
            )
        self._ensure_dir()
        file_path = self.memory_dir / filename
        # Ensure description is single line
        description = description.replace("\n", " ").strip()
        frontmatter = (
            f"---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"type: {memory_type}\n"
            f"---\n\n"
        )
        file_path.write_text(frontmatter + content, encoding="utf-8")
        self.rebuild_ledger()
        return file_path

    def rebuild_ledger(self) -> None:
        """
        Scan all .md files in memory/, rebuild MEMORY.md index.
        Format: - [name](filename) — description
        """
        self._ensure_dir()
        entries = []
        for md_file in sorted(self.memory_dir.glob("*.md")):
            if md_file.name == LEDGER_NAME:
                continue
            header = self._parse_frontmatter(md_file)
            if header:
                entries.append(
                    f"- [{header.get('name', md_file.stem)}]({md_file.name})"
                    f" \u2014 {header.get('description', 'No description')}"
                )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            f"# Memory: {self.workload_name}",
            f"<!-- Last rebuilt: {now} -->",
            "",
        ]
        lines.extend(entries)
        content = "\n".join(lines) + "\n"

        # Enforce caps
        if len(content.encode("utf-8")) > LEDGER_BYTE_CAP:
            content = content.encode("utf-8")[:LEDGER_BYTE_CAP].decode(
                "utf-8", errors="ignore"
            )
        result_lines = content.splitlines(keepends=True)
        if len(result_lines) > LEDGER_LINE_CAP:
            content = "".join(result_lines[:LEDGER_LINE_CAP])

        self.ledger_path.write_text(content, encoding="utf-8")

    def survey(self) -> List[Dict[str, str]]:
        """
        Scan all .md files, read frontmatter only (not body content).
        Returns list of {filename, name, description, type, mtime}.
        Excludes MEMORY.md itself.
        """
        results = []
        if not self.memory_dir.exists():
            return results
        for md_file in sorted(self.memory_dir.glob("*.md")):
            if md_file.name == LEDGER_NAME:
                continue
            header = self._parse_frontmatter(md_file)
            if header:
                header["filename"] = md_file.name
                header["mtime"] = datetime.fromtimestamp(
                    md_file.stat().st_mtime, tz=timezone.utc
                ).isoformat()
                results.append(header)
        return results

    def recall(self, filename: str) -> str:
        """Load full content of a specific memory file."""
        path = self.memory_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Memory file not found: {path}")
        return path.read_text(encoding="utf-8")

    def compose_injection(self, selected_filenames: List[str]) -> str:
        """
        Build the memory section for sub-agent system prompt injection.
        Includes the ledger index + full content of selected files only.
        """
        parts = [f"## Memory for {self.workload_name}\n"]

        ledger = self.read_ledger()
        if ledger:
            parts.append(ledger)
            parts.append("")

        if selected_filenames:
            parts.append("### Selected Memory Files\n")
            for fname in selected_filenames:
                try:
                    content = self.recall(fname)
                    header = self._parse_frontmatter(self.memory_dir / fname)
                    mem_type = (
                        header.get("type", "unknown") if header else "unknown"
                    )
                    parts.append(f"**{fname}** ({mem_type})")
                    # Strip frontmatter from display
                    body = self._strip_frontmatter(content)
                    parts.append(body.strip())
                    parts.append("")
                except FileNotFoundError:
                    continue

        return "\n".join(parts)

    @staticmethod
    def _parse_frontmatter(path: Path) -> Optional[Dict[str, str]]:
        """Parse YAML frontmatter from a file. Returns None if no frontmatter."""
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        if not text.startswith("---"):
            return None
        end = text.find("---", 3)
        if end == -1:
            return None
        try:
            return yaml.safe_load(text[3:end])
        except yaml.YAMLError:
            return None

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        """Remove YAML frontmatter from text."""
        if not text.startswith("---"):
            return text
        end = text.find("---", 3)
        if end == -1:
            return text
        return text[end + 3 :].lstrip("\n")
