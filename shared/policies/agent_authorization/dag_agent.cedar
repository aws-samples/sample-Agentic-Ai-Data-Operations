// DAG Agent: writes the DAG spec under config/, renders dags/{workload}_dag.py, and its tests (Step 4.5).
// Writes are an allowlist of file types; anything else is denied.

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
    resource.fileType == "dag" || resource.fileType == "config" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"dag",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
unless {
    resource.fileType == "dag" || resource.fileType == "config" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
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
    action == DataOnboarding::Action::"PromoteData",
    resource
);

// Sub-agents have no MCP or AWS access (includes the aws CLI via a shell).
forbid (
    principal == DataOnboarding::AgentPrincipal::"dag",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
