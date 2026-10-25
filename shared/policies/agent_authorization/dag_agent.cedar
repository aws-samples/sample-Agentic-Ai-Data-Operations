// DAG Agent: reads all configs, writes DAG files only, no direct data access
permit (
    principal == DataOnboarding::AgentPrincipal::"dag",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"dag",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "dag"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"dag",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType != "dag"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"dag",
    action == DataOnboarding::Action::"ReadData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"dag",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"dag",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
