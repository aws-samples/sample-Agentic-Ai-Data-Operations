// Router Agent: read-only gatekeeper — can read all files, cannot write anything or invoke MCP
permit (
    principal == DataOnboarding::AgentPrincipal::"router",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"router",
    action == DataOnboarding::Action::"ReadData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"router",
    action == DataOnboarding::Action::"WriteFile",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"router",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"router",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"router",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
