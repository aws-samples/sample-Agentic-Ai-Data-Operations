"""Shared guard: the plugin's hooks stand down inside an ADOP checkout.

Plugin components are namespaced — an agent arrives as `adop:metadata-agent`, a command
as `/adop:onboard-workflow` — so they cannot shadow a repository's own. **Hooks are the
exception.** They carry no namespace: every matching hook fires, so a plugin hook runs
*in addition to* whatever the project already has.

Verified by install: the hook count went 5 -> 6 when this plugin was added to an ADOP
checkout, purely additive.

That is the one way this plugin could affect a repository's own `/onboard-workflow`, and
it is what these guards prevent. When the project already ships the equivalent hook, the
plugin's copy exits 0 without output and the project's wins. Outside a checkout — a user's
own data repository, which is what the plugin is for — nothing matches and the plugin's
hook does its job.

Deliberately conservative in two ways:

- It looks for the *specific* counterpart file, not merely a `.claude/hooks/` directory,
  so a project with its own unrelated hooks still gets the plugin's protection.
- It checks the working directory rather than trying to detect "am I in the ADOP repo",
  which would need a marker the plugin cannot rely on.
"""
import os
from pathlib import Path


def project_hook_present(*names: str) -> bool:
    """True when the working directory already ships one of these hooks.

    Accepts several names because a plugin hook may supersede a project hook of a
    different filename — the plugin's Python port of `check-discovery-gate.sh`, for
    instance, stands down for the shell original.
    """
    hooks = Path(os.getcwd()) / ".claude" / "hooks"
    return any((hooks / n).is_file() for n in names)


def stand_down_if_project_owns(*names: str) -> bool:
    """Call at the top of a hook. Returns True if the caller should exit quietly.

    Usage:

        if stand_down_if_project_owns("enforce_template_codegen.py"):
            print("{}")
            raise SystemExit(0)
    """
    return project_hook_present(*names)
