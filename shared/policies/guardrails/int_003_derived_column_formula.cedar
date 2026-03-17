// INT-003: Forbid promotion if derived column formula is not verified
forbid (
    principal,
    action == DataOnboarding::Action::"PassIntegrityCheck",
    resource
)
when {
    context.guardrailCode == "INT-003" &&
    context.formulaVerified == false
};
