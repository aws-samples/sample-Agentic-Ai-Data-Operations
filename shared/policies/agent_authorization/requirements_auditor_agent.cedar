// Requirements Auditor: evidence-only workflow conformance gate.
// It can inspect run state and artifacts and write only its audit report.

permit (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "audit"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType != "audit"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"ReadData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"requirements_auditor",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
