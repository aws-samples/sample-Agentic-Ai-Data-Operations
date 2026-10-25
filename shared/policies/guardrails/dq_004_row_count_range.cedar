// DQ-004: Forbid promotion if output has zero rows
forbid (
    principal,
    action == DataOnboarding::Action::"PassQualityGate",
    resource
)
when {
    context.guardrailCode == "DQ-004" &&
    context.rowCountAboveZero == false
};
