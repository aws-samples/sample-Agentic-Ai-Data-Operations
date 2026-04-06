"""
Adaptive Prompt Registry — stores and applies learned prompt patches.

Structured files with frontmatter, an index that tracks all entries,
and auto-application above a confidence gate.

Storage layout:
    shared/prompt_intelligence/patches/
    |-- PATCH_INDEX.md              <-- index of all patches
    |-- ph1_pk_discovery.patch      <-- individual patch files
    |-- ph4_null_handling.patch

Patch file format:
    ---
    patch_id: abc123
    pattern_id: <from CrossWorkloadPattern>
    agent_type: metadata
    phase: 1
    skills_section: "Phase 1: Discovery"
    confidence: 0.85
    frequency: 7
    status: pending|applied|rejected
    applied_at: null
    ---
    [patch text]
"""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from .schemas import CrossWorkloadPattern

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_GATE = 0.80
PATCH_DIR = Path(__file__).resolve().parent / "patches"
PATCH_INDEX_NAME = "PATCH_INDEX.md"
VALID_STATUSES = {"pending", "applied", "rejected"}


# ---------------------------------------------------------------------------
# Helpers (module-level)
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert text to a snake_case, filename-safe string."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    # collapse repeated underscores
    text = re.sub(r"_+", "_", text)
    return text


class PromptEvolver:
    """Evolves prompts by harvesting cross-workload failure insights
    and grafting corrective patches into SKILLS.md."""

    def __init__(self, repo_root: Path = None):
        if repo_root is None:
            # 3 levels up: patch_registry.py -> prompt_intelligence -> shared -> repo_root
            repo_root = Path(__file__).resolve().parent.parent.parent
        self.repo_root = Path(repo_root)
        self.patch_dir = self.repo_root / "shared" / "prompt_intelligence" / "patches"
        self.patch_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def harvest_insights(
        self,
        cross_patterns: List[CrossWorkloadPattern],
        auto_graft: bool = True,
    ) -> Dict[str, int]:
        """Ingest cross-workload patterns and create patch files.

        For each pattern that carries a ``prompt_patch``:
        1. Skip if a .patch file for its pattern_id already exists.
        2. Write a new .patch file with YAML frontmatter.
        3. If confidence >= CONFIDENCE_GATE and *auto_graft*, graft it.
        4. Rebuild the index.

        Returns counts: harvested, grafted, pending, duplicates_skipped.
        """
        harvested = 0
        grafted = 0
        pending = 0
        duplicates_skipped = 0

        for pattern in cross_patterns:
            if not pattern.prompt_patch:
                continue

            # Check for existing patch with same pattern_id
            if self._patch_exists_for_pattern(pattern.pattern_id):
                duplicates_skipped += 1
                continue

            # Build filename
            slug = _slugify(
                f"ph{pattern.phase}_{pattern.agent_type}_{pattern.signature[:40]}"
            )
            filename = f"{slug}.patch"

            patch_id = uuid.uuid4().hex[:12]

            frontmatter = {
                "patch_id": patch_id,
                "pattern_id": pattern.pattern_id,
                "agent_type": pattern.agent_type,
                "phase": pattern.phase,
                "skills_section": pattern.prompt_section,
                "confidence": round(pattern.confidence, 4),
                "frequency": pattern.frequency,
                "status": "pending",
                "applied_at": None,
            }

            self._write_patch_file(filename, frontmatter, pattern.prompt_patch)
            harvested += 1

            if auto_graft and pattern.confidence >= CONFIDENCE_GATE:
                success = self.graft_patch(patch_id)
                if success:
                    grafted += 1
                else:
                    pending += 1
            else:
                pending += 1

        self.rebuild_index()

        return {
            "harvested": harvested,
            "grafted": grafted,
            "pending": pending,
            "duplicates_skipped": duplicates_skipped,
        }

    def graft_patch(self, patch_id: str, skills_path: Path = None) -> bool:
        """Apply a patch to SKILLS.md by inserting it under the matching section.

        Returns True on success, False if the section was not found or the
        patch was already grafted (idempotent).
        """
        patch_path = self._find_patch_by_id(patch_id)
        if patch_path is None:
            return False

        fm = self._read_patch_frontmatter(patch_path)
        body = self._read_patch_body(patch_path)
        skills_section = fm.get("skills_section", "")

        if skills_path is None:
            skills_path = self.repo_root / "SKILLS.md"

        if not skills_path.exists():
            return False

        skills_text = skills_path.read_text(encoding="utf-8")

        # Already grafted?
        graft_marker = f"<!-- GRAFT: {patch_id}"
        if graft_marker in skills_text:
            return False

        # Find section header (## or ###)
        section_pattern = re.compile(
            rf"^(#{{2,3}})\s+{re.escape(skills_section)}\s*$", re.MULTILINE
        )
        match = section_pattern.search(skills_text)
        if match is None:
            return False

        header_level = match.group(1)
        section_start = match.end()

        # Find next section of same or higher level
        next_section = re.compile(
            rf"^#{{{1},{len(header_level)}}}\s+", re.MULTILINE
        )
        next_match = next_section.search(skills_text, section_start + 1)

        insert_pos = next_match.start() if next_match else len(skills_text)

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        block = (
            f"\n<!-- GRAFT: {patch_id} applied {now_iso} -->\n"
            f"{body}\n"
            f"<!-- END GRAFT: {patch_id} -->\n"
        )

        new_text = skills_text[:insert_pos] + block + skills_text[insert_pos:]
        skills_path.write_text(new_text, encoding="utf-8")

        # Update patch status
        fm["status"] = "applied"
        fm["applied_at"] = now_iso
        self._write_patch_file(patch_path.name, fm, body)

        self.rebuild_index()
        return True

    def prune_patch(self, patch_id: str, skills_path: Path = None) -> bool:
        """Remove a previously grafted patch from SKILLS.md.

        Resets patch status to 'pending'.
        Returns True if the graft block was found and removed, False otherwise.
        """
        if skills_path is None:
            skills_path = self.repo_root / "SKILLS.md"

        if not skills_path.exists():
            return False

        skills_text = skills_path.read_text(encoding="utf-8")

        # Match the full graft block including surrounding newlines
        graft_pattern = re.compile(
            rf"\n?<!-- GRAFT: {re.escape(patch_id)} applied [^>]* -->\n"
            rf".*?\n"
            rf"<!-- END GRAFT: {re.escape(patch_id)} -->\n?",
            re.DOTALL,
        )

        new_text, count = graft_pattern.subn("", skills_text)

        if count == 0:
            return False

        skills_path.write_text(new_text, encoding="utf-8")

        # Reset patch status
        patch_path = self._find_patch_by_id(patch_id)
        if patch_path:
            fm = self._read_patch_frontmatter(patch_path)
            body = self._read_patch_body(patch_path)
            fm["status"] = "pending"
            fm["applied_at"] = None
            self._write_patch_file(patch_path.name, fm, body)

        self.rebuild_index()
        return True

    def census(self, status: str = None) -> List[Dict[str, Any]]:
        """List all patches, optionally filtered by status."""
        results = []
        for pf in sorted(self.patch_dir.glob("*.patch")):
            fm = self._read_patch_frontmatter(pf)
            if status and fm.get("status") != status:
                continue
            results.append(fm)
        return results

    def tally(self) -> Dict[str, int]:
        """Return aggregate counts by status."""
        counts = {"total": 0, "applied": 0, "pending": 0, "rejected": 0}
        for pf in self.patch_dir.glob("*.patch"):
            fm = self._read_patch_frontmatter(pf)
            counts["total"] += 1
            s = fm.get("status", "pending")
            if s in counts:
                counts[s] += 1
        return counts

    def rebuild_index(self) -> None:
        """Regenerate PATCH_INDEX.md from all .patch files."""
        lines = ["# Prompt Patch Index\n"]
        patches = sorted(self.patch_dir.glob("*.patch"))

        if not patches:
            lines.append("No patches registered yet.\n")
        else:
            for pf in patches:
                fm = self._read_patch_frontmatter(pf)
                pid = fm.get("patch_id", "unknown")
                section = fm.get("skills_section", "unknown")
                conf = fm.get("confidence", 0)
                status = fm.get("status", "pending")
                lines.append(
                    f"- [{pid}]({pf.name}) "
                    f"-- {section} | confidence={conf} | {status}"
                )
            lines.append("")  # trailing newline

        index_path = self.patch_dir / PATCH_INDEX_NAME
        index_path.write_text("\n".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _patch_exists_for_pattern(self, pattern_id: str) -> bool:
        """Return True if any .patch file references this pattern_id."""
        for pf in self.patch_dir.glob("*.patch"):
            fm = self._read_patch_frontmatter(pf)
            if fm.get("pattern_id") == pattern_id:
                return True
        return False

    def _find_patch_by_id(self, patch_id: str) -> Optional[Path]:
        """Find the .patch file with the given patch_id."""
        for pf in self.patch_dir.glob("*.patch"):
            fm = self._read_patch_frontmatter(pf)
            if fm.get("patch_id") == patch_id:
                return pf
        return None

    def _read_patch_frontmatter(self, patch_path: Path) -> Dict[str, Any]:
        """Parse YAML frontmatter from a .patch file."""
        text = patch_path.read_text(encoding="utf-8")
        fm: Dict[str, Any] = {}

        if not text.startswith("---"):
            return fm

        end = text.find("---", 3)
        if end == -1:
            return fm

        fm_text = text[3:end].strip()
        for line in fm_text.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            # Type coercion
            if value == "null" or value == "None" or value == "":
                value = None
            elif value == "true":
                value = True
            elif value == "false":
                value = False
            else:
                try:
                    if "." in str(value):
                        value = float(value)
                    else:
                        value = int(value)
                except (ValueError, TypeError):
                    pass

            fm[key] = value

        # Ensure ID fields are always strings (hex IDs may look numeric)
        for id_key in ("patch_id", "pattern_id"):
            if id_key in fm and fm[id_key] is not None:
                fm[id_key] = str(fm[id_key])

        return fm

    def _read_patch_body(self, patch_path: Path) -> str:
        """Read patch body (everything after the second ---)."""
        text = patch_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return text

        end = text.find("---", 3)
        if end == -1:
            return text

        return text[end + 3:].strip()

    def _write_patch_file(
        self, filename: str, frontmatter: Dict[str, Any], body: str
    ) -> None:
        """Write a .patch file with YAML frontmatter and body."""
        lines = ["---"]
        for key, value in frontmatter.items():
            if value is None:
                lines.append(f"{key}: null")
            elif isinstance(value, bool):
                lines.append(f"{key}: {'true' if value else 'false'}")
            elif isinstance(value, str) and " " in value:
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        lines.append(body)
        lines.append("")  # trailing newline

        path = self.patch_dir / filename
        path.write_text("\n".join(lines), encoding="utf-8")
