// IaC Agent: generates workloads/{name}/iac/** (Terraform / CDK / CloudFormation + APPLY_GUIDE.md). Generation only; never applies. Cedar permits it drafts are staged under iac/ for a human to promote into shared/policies/.
// Writes are an allowlist of file types; anything else is denied.

permit (
    principal == DataOnboarding::AgentPrincipal::"iac",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"iac",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "iac" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"iac",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
unless {
    resource.fileType == "iac" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"iac",
    action == DataOnboarding::Action::"ReadData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"iac",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"iac",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

// Sub-agents have no MCP or AWS access (includes the aws CLI via a shell).
forbid (
    principal == DataOnboarding::AgentPrincipal::"iac",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
