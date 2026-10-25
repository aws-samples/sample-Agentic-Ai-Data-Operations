// Onboarding Agent: orchestrator with full access — runs in main conversation
permit (
    principal == DataOnboarding::AgentPrincipal::"onboarding",
    action,
    resource
)
when {
    principal.executionContext == "main_conversation"
};
