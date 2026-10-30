// Transformation Agent: writes config/transformations.yaml, renders scripts/transform/* and sql/*, and its tests (Step 4.3).
// Writes are an allowlist of file types; anything else is denied.

permit (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "config" || resource.fileType == "script" || resource.fileType == "sql" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
unless {
    resource.fileType == "config" || resource.fileType == "script" || resource.fileType == "sql" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

permit (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"ReadData",
    resource
)
when {
    resource.zone == "landing" || resource.zone == "staging"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

// Sub-agents have no MCP or AWS access (includes the aws CLI via a shell).
forbid (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
