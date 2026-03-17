// Analysis Agent: reads publish zone only, cannot write anything
permit (
    principal == DataOnboarding::AgentPrincipal::"analysis",
    action == DataOnboarding::Action::"ReadData",
    resource
)
when {
    resource.zone == "publish"
};

permit (
    principal == DataOnboarding::AgentPrincipal::"analysis",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"analysis",
    action == DataOnboarding::Action::"ReadData",
    resource
)
when {
    resource.zone == "landing" || resource.zone == "staging"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"analysis",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"analysis",
    action == DataOnboarding::Action::"WriteFile",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"analysis",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
