// Metadata Agent: reads landing/staging data, writes config files only, no MCP
permit (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"ReadData",
    resource
)
when {
    resource.zone == "landing" || resource.zone == "staging"
};

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
    resource.fileType == "config"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType != "config"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"metadata",
    action == DataOnboarding::Action::"WriteData",
    resource
)
when {
    resource.zone == "publish"
};
