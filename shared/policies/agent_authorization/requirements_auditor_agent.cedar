// Requirements Auditor: writes run/requirements_audit.json and appends run/decisions.jsonl and logs/trace_events.jsonl. Read-only over every pipeline artifact.
// Writes are an allowlist of file types; anything else is denied.

permit (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "audit" || resource.fileType == "decisions" || resource.fileType == "log"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
unless {
    resource.fileType == "audit" || resource.fileType == "decisions" || resource.fileType == "log"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"ReadData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

// Sub-agents have no MCP or AWS access (includes the aws CLI via a shell).
forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
