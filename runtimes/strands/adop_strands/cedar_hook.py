"""Cedar enforcement for the Strands runtime.

Uses Strands' own hook API: a `HookProvider` registered on every `Agent`
handles `BeforeToolCallEvent` and sets `cancel_tool` when Cedar denies the
call. The decision comes from `shared/utils/cedar_gate.decide()`, the same
engine the Claude Code, Codex and Kiro `cedar_gate.py` hooks call, so a tool
call gets the same verdict on all four runtimes.

Strands also ships `strands.vended_interventions.cedar`; it is not used here
because it generates its own schema from tool signatures and resolves
principals differently, which would make Strands decisions diverge from the
other platforms for the same policies.

The tool-level guards in `tools.py` stay in place as a second layer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

Decider = Callable[[dict, Optional[str]], Tuple[bool, str, dict]]


def _load_decider(repo_root: Path) -> Decider:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from shared.utils.cedar_gate import decide

    return decide


class CedarToolGate:
    """Strands HookProvider: deny tool calls the Cedar policies forbid."""

    def __init__(self, repo_root: Path, principal: str, decider: Optional[Decider] = None):
        self.repo_root = Path(repo_root).resolve()
        self.principal = principal
        self.decider = decider or _load_decider(self.repo_root)
        self.denials: list[str] = []

    def register_hooks(self, registry: Any, **_: Any) -> None:
        from strands.hooks import BeforeToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self.before_tool_call)

    def before_tool_call(self, event: Any) -> None:
        tool_use = event.tool_use or {}
        payload = {
            "tool_name": tool_use.get("name", ""),
            "tool_input": tool_use.get("input") or {},
            "cwd": str(self.repo_root),
            "hook_event_name": "PreToolUse",
            "runtime": "strands",
        }
        try:
            allowed, reason, _ = self.decider(payload, self.principal)
        except Exception as exc:  # the gate must never resolve to "allow" on failure
            allowed, reason = False, f"Cedar gate failed: {type(exc).__name__}: {exc}"
        if not allowed:
            self.denials.append(reason)
            event.cancel_tool = reason
