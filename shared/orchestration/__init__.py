"""ADOP orchestration driver for Amazon Q Developer CLI.

Phase 4 of the Claude Code -> Amazon Q Developer CLI migration. Provides the
external driver that replaces Claude Code's `Workflow`-tool DSL by shelling out
to `q chat --agent <name> --no-interactive` per phase, with sequential and
parallel execution, test gates, and a schema-validated-handoff success contract.

See `.amazonq/cli-agents/README.md` and `ADOP-to-AmazonQ-Migration-Design.md`.
"""

from shared.orchestration.workflow_driver import (
    AgentInvocation,
    AgentResult,
    WorkflowDriver,
    build_model_for_regulation,
)

__all__ = [
    "AgentInvocation",
    "AgentResult",
    "WorkflowDriver",
    "build_model_for_regulation",
]
