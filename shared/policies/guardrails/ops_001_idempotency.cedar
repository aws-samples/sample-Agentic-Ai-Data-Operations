// OPS-001: Forbid promotion if re-run checksum does not match
forbid (
    principal,
    action == DataOnboarding::Action::"PassOperationalCheck",
    resource
)
when {
    context.guardrailCode == "OPS-001" &&
    context.checksumMatch == false
};
