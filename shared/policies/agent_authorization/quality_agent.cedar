// Quality Agent: reads all zones, writes quality rules config only, no data modification
permit (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"ReadData",
    resource
);

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
    resource.fileType == "config"
};

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

forbid (
    principal == DataOnboarding::AgentPrincipal::"quality",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
