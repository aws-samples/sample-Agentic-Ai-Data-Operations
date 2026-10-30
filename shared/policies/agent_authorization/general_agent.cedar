// General agents: any agent with no ADOP-specific principal (Explore,
// general-purpose, plugin and helper agents). Human decision 2026-10-30:
// "It should write access workloads folder but not policy editing."
// Policy files and the deploy gate are forbidden for everyone in
// global_protection.cedar. Run-state and audit records are forbidden here
// because writing them would forge a human gate (discovery, audit).

permit (
    principal == DataOnboarding::AgentPrincipal::"general",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"general",
    action == DataOnboarding::Action::"WriteFile",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"general",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "run_state" || resource.fileType == "audit"
};

permit (
    principal == DataOnboarding::AgentPrincipal::"general",
    action == DataOnboarding::Action::"ReadData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"general",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"general",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"general",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
