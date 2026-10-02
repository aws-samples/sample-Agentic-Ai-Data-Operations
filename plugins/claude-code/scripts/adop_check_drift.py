#!/usr/bin/env python3
"""Check rendered artifacts against their specs and report any that were hand-edited.

The companion to `adop_render.py`. Rendering writes a five-line provenance header —
spec_hash, template_id, template_hash, schema_version, rendered_at — and this re-renders
from the spec and compares, so an artifact someone edited by hand is detectable rather
than merely discouraged.

Usage:

    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/adop_check_drift.py" workloads/claims
    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/adop_check_drift.py" workloads/*

Exits 0 when every artifact matches its spec, 1 on drift. Pass `--pre-commit` with explicit
file paths to check only those, which is how a git hook would call it.

## Why this exists as a separate entry point

In an ADOP checkout the validator is reachable as `python -m shared.codegen.drift_validator`,
which is how `.pre-commit-config.yaml` and the `Validate Prompts` workflow invoke it. A user's
own repository has no importable `shared`, so — exactly as with the renderer — the plugin
vendors the module under `lib/` and exposes it here.

## Why drift matters more in the plugin than in the repo

The repository has a CI job running this on every PR. A plugin cannot install CI into someone's
repository, so nothing runs it automatically: the PreToolUse hook prevents an agent writing to
`workloads/*/{scripts,dags,sql}/` at all, and this is how you check artifacts that were already
written — after a hand edit, a template upgrade, or a spec change that should have been
re-rendered. Worth running before promoting anything.

An artifact reported as drifted is not repaired by editing it. Re-render it from its spec, which
is the only operation that restores a valid header.
"""
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

from shared.codegen.drift_validator import (  # noqa: E402
    main as drift_main,
    parse_artifact_header,
)

ARTIFACT_DIRS = ("scripts", "dags", "sql")
ARTIFACT_SUFFIXES = (".py", ".sql", ".yaml", ".yml")


def _paths() -> list[str]:
    return [a for a in sys.argv[1:] if not a.startswith("-")]


def _explain_if_no_args() -> bool:
    """The validator exits 0 on an empty argument list, which reads as a pass.

    That vacuous-pass shape is why the repository's own CI job enumerates workload
    directories explicitly before calling it. Refuse rather than silently succeed.
    """
    if _paths():
        return False
    print(
        "error: no paths given.\n"
        "       Pass workload directories or artifact paths, for example:\n"
        "         adop_check_drift.py workloads/claims\n"
        "         adop_check_drift.py workloads/*\n"
        "       An empty argument list would exit 0 without checking anything, which\n"
        "       reads as a pass — so it is refused instead.",
        file=sys.stderr,
    )
    return True


def _count_artifacts(paths: list[str]) -> int:
    """How many provenance-headed artifacts the given paths actually contain.

    Guarding the empty *argument* list above was only half the job: arguments that
    resolve to zero artifacts hit the same wall one level in. `adop_check_drift.py
    workloads/sales` on a workload whose artifacts are absent, or sit somewhere other
    than scripts/dags/sql, printed nothing and exited 0 — indistinguishable from
    "six artifacts, all clean". Found by running this tool against a freshly rendered
    workload during end-to-end testing and noticing it reported success without
    naming a single file.

    Deliberately mirrors `verify_workload`'s own rule — the three directories, the four
    suffixes, and a parsable header — by importing `parse_artifact_header` rather than
    re-implementing it, so the count cannot disagree with what the validator inspects.
    """
    total = 0
    for raw in paths:
        p = Path(raw)
        candidates: list[Path] = []
        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            for subdir in ARTIFACT_DIRS:
                d = p / subdir
                if d.is_dir():
                    candidates.extend(
                        f for f in d.rglob("*")
                        if f.is_file() and f.suffix in ARTIFACT_SUFFIXES
                    )
        for f in candidates:
            try:
                if parse_artifact_header(f.read_text(encoding="utf-8")) is not None:
                    total += 1
            except (OSError, UnicodeDecodeError):
                continue
    return total


if __name__ == "__main__":
    if _explain_if_no_args():
        sys.exit(2)

    given = _paths()
    if _count_artifacts(given) == 0:
        print(
            "error: no rendered artifacts found under: " + ", ".join(given) + "\n"
            "       Looked for .py/.sql/.yaml/.yml files carrying a 5-line provenance\n"
            "       header under scripts/, dags/ and sql/ — the only files this can check.\n"
            "       Nothing to check is not the same as nothing wrong, so this is an error\n"
            "       rather than a silent pass. Either the path is wrong, or the artifacts\n"
            "       were never rendered — run adop_render.py first.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(drift_main() or 0)
