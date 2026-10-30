// Metadata Agent: writes config/source.yaml and its tests (Phase 3, Step 4.2).
// Writes are an allowlist of file types; anything else is denied.

permit (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "config" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
unless {
    resource.fileType == "config" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

permit (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"ReadData",
    resource
)
when {
    resource.zone == "landing" || resource.zone == "staging"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

// Phase 3 profiling (Strands): only the fixed read-only aws_ro_* tools
// (Glue get_*, S3 list/sample, Athena single SELECT). No MCP, no aws CLI.
permit (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"InvokeTool",
    resource
)
when {
    resource.serverName == "aws-readonly"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"InvokeTool",
    resource
)
unless {
    resource.serverName == "aws-readonly"
};
