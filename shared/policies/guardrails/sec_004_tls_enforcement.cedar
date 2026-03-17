// SEC-004: Forbid proceeding if TLS is not enforced
forbid (
    principal,
    action == DataOnboarding::Action::"PassSecurityCheck",
    resource
)
when {
    context.guardrailCode == "SEC-004" &&
    context.tlsEnforced == false
};
