// Quality Agent: writes config/quality_rules.yaml, renders scripts/quality/*, and its tests (Step 4.4).
// Writes are an allowlist of file types; anything else is denied.

permit (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "config" || resource.fileType == "script" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
unless {
    resource.fileType == "config" || resource.fileType == "script" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

permit (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"ReadData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

// Sub-agents have no MCP or AWS access (includes the aws CLI via a shell).
forbid (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
