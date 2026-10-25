// OPS-002: Forbid promotion if encryption was not re-keyed at zone boundary
forbid (
    principal,
    action == DataOnboarding::Action::"PassOperationalCheck",
    resource
)
when {
    context.guardrailCode == "OPS-002" &&
    context.keysAreDifferent == false
};
