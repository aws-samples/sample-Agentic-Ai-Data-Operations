// Transformation Agent: reads landing/staging data, writes scripts + SQL, no publish zone
permit (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"ReadData",
    resource
)
when {
    resource.zone == "landing" || resource.zone == "staging"
};

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
    resource.fileType == "script" || resource.fileType == "sql"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"WriteData",
    resource
)
when {
    resource.zone == "publish"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"transformation",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
