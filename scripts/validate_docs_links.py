#!/usr/bin/env python3
"""Validate that file paths referenced in docs and prompts actually exist.

Two classes of reference rot this catches:

1. **Markdown links** — `[text](relative/path.md)`, resolved against the linking file.
2. **Bare repo paths** — `runbooks/foo.md`, `.claude/agents/dag-agent.md`, `shared/x.py`,
   whether in prose, tables, or backticks.

Class 2 is the dangerous one. The orchestrator loads a regulation control set by `Read`-ing a
hardcoded path out of `SKILLS.md`. A wrong path fails at read time and the orchestrator carries
on *without* the compliance controls — silently. Nothing else in CI notices.

Also checks that every regulation is registered in all four places that must agree.

Exit 0 clean, 1 on any broken reference.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories that referenced paths are expected to live under. A candidate path must start
# with one of these; anything else (URLs, package names, arbitrary prose) is ignored.
#
# Deliberately excluded, because a hit there is almost always an illustrative example rather
# than a claim about the repo:
#   workloads/  - per-run, generated; `workloads/order_transactions/...` is a worked example
#   scripts/    - inside a workload, `scripts/transform/x.py` is workload-relative
#   tests/      - same
#   agentcore/  - runbook-relative, and several entries are artifacts the runbook creates
REPO_PREFIXES = (
    ".claude/", ".github/", "contracts/", "docs/", "mcp-servers/", "runbooks/",
    "shared/", "tool-registry/",
)

# Extensions worth resolving. Keeps prose like "shared/utils/" out of the candidate set while
# still catching the file references that actually break things.
CHECKED_SUFFIXES = (
    ".md", ".py", ".yaml", ".yml", ".json", ".sql", ".j2", ".ttl", ".sh", ".html", ".csv",
)

# Files scanned for references. Prose and prompts only — `.py` sources put paths in string
# literals and regexes, which produce noise, and a wrong path in code fails loudly anyway.
SCANNED_SUFFIXES = (".md", ".html")

# Directories excluded from scanning: dated snapshots that describe the repo as it was.
SKIPPED_DIRS = ("docs/prompt_intelligence/",)

# Substrings that mark a candidate as a template or example rather than a real path.
TEMPLATE_MARKERS = ("{", "}", "*", "$", "<", ">", "...", "|", "YYYY", "MM-DD")

# Paths that prose deliberately names as *absent* — the point of the sentence is that the file
# does not exist. Rather than exempt them, the check is inverted below: if one of these ever
# appears on disk the validator fails, so the prose gets corrected instead of quietly rotting.
ASSERTED_MISSING = {
    # Named in CLAUDE.md, README.md and SKILLS.md but never written; the check logic lives in
    # the rendered output of shared/templates/quality_check.py.j2. Sub-agents are told not to
    # import it and not to create it as a side effect.
    "shared/utils/quality_checks.py",
}

BARE_PATH_RE = re.compile(
    r"(?<![\w./-])((?:" + "|".join(re.escape(p) for p in REPO_PREFIXES) + r")[\w./@-]+)"
)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

REGULATIONS = {
    # file stem -> (SKILLS.md dispatch spelling, schema enum value)
    "gdpr": ("gdpr.md", "GDPR"),
    "ccpa": ("ccpa.md", "CCPA"),
    "hipaa": ("hipaa.md", "HIPAA"),
    "sox": ("sox.md", "SOX"),
    "pci-dss": ("pci-dss.md", "PCI_DSS"),
}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    )
    return [PROJECT_ROOT / line for line in out.stdout.splitlines() if line]


def is_candidate(raw: str) -> bool:
    if any(m in raw for m in TEMPLATE_MARKERS):
        return False
    return raw.endswith(CHECKED_SUFFIXES)


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(errors="ignore")
    except OSError as e:
        return [f"{path}: unreadable: {e}"]

    rel = path.relative_to(PROJECT_ROOT)
    in_fence = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        # Paths inside fenced blocks are commands, heredocs, and ASCII diagrams — often naming
        # a file the block itself creates. Only prose and tables make a cross-reference claim.
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        for raw in BARE_PATH_RE.findall(line):
            raw = raw.rstrip(".,;:)`\"'")
            if not is_candidate(raw) or raw in ASSERTED_MISSING:
                continue
            if not (PROJECT_ROOT / raw).exists():
                errors.append(f"{rel}:{lineno}: broken repo path -> {raw}")

        for link in MD_LINK_RE.findall(line):
            link = link.split("#", 1)[0]
            if not link or link.startswith(("http://", "https://", "mailto:")):
                continue
            if any(m in link for m in TEMPLATE_MARKERS):
                continue
            if link.startswith(REPO_PREFIXES):
                continue  # already covered by the bare-path pass
            target = (path.parent / link).resolve()
            if not target.exists():
                errors.append(f"{rel}:{lineno}: broken relative link -> {link}")

    return errors


def check_regulation_registry() -> list[str]:
    """A regulation must appear in all four places, or it silently never applies."""
    errors: list[str] = []
    reg_dir = PROJECT_ROOT / "runbooks/data-onboarding-agent/regulation"
    skills = (PROJECT_ROOT / "SKILLS.md").read_text(errors="ignore")
    picker = (reg_dir / "README.md").read_text(errors="ignore")
    schema_path = PROJECT_ROOT / "contracts/v1/quality_spec.schema.json"
    schema_text = json.dumps(json.loads(schema_path.read_text()))

    for stem, (filename, enum_value) in REGULATIONS.items():
        if not (reg_dir / filename).exists():
            errors.append(f"regulation {stem}: missing {reg_dir.name}/{filename}")
        if filename not in skills:
            errors.append(f"regulation {stem}: not in the SKILLS.md dispatch list")
        if filename not in picker:
            errors.append(f"regulation {stem}: not in regulation/README.md picker table")
        if f'"{enum_value}"' not in schema_text:
            errors.append(
                f"regulation {stem}: {enum_value} absent from quality_spec.schema.json"
            )
    return errors


def check_asserted_missing() -> list[str]:
    """Inverse check: prose claims these do not exist, so fail if one shows up."""
    return [
        f"{rel} now exists, but prose in .claude/agents/ and docs asserts it does not — "
        f"update those references and drop it from ASSERTED_MISSING"
        for rel in sorted(ASSERTED_MISSING)
        if (PROJECT_ROOT / rel).exists()
    ]


def main() -> int:
    errors: list[str] = []
    for path in tracked_files():
        if path.suffix not in SCANNED_SUFFIXES or not path.exists():
            continue
        if str(path.relative_to(PROJECT_ROOT)).startswith(SKIPPED_DIRS):
            continue
        errors.extend(check_file(path))

    errors.extend(check_regulation_registry())
    errors.extend(check_asserted_missing())

    if errors:
        print(f"FAIL: {len(errors)} broken reference(s)\n")
        for e in errors:
            print(f"  {e}")
        print(
            "\nA broken prompt path does not raise — the orchestrator reads it, fails, and "
            "continues without the content. Fix the path or delete the reference."
        )
        return 1

    print("OK: all referenced paths resolve; all 5 regulations registered in 4 places")
    return 0


if __name__ == "__main__":
    sys.exit(main())
