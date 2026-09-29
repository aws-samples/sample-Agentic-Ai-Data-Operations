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

from shared.codegen.drift_validator import main as drift_main  # noqa: E402


def _explain_if_no_args() -> bool:
    """The validator exits 0 on an empty argument list, which reads as a pass.

    That vacuous-pass shape is why the repository's own CI job enumerates workload
    directories explicitly before calling it. Refuse rather than silently succeed.
    """
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
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


if __name__ == "__main__":
    if _explain_if_no_args():
        sys.exit(2)
    sys.exit(drift_main() or 0)
