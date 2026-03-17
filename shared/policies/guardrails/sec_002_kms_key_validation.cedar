// SEC-002: Forbid proceeding if KMS key alias is invalid
forbid (
    principal,
    action == DataOnboarding::Action::"PassSecurityCheck",
    resource
)
when {
    context.guardrailCode == "SEC-002" &&
    context.kmsAliasValid == false
};
