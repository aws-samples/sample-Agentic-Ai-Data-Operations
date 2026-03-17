// DQ-002: Forbid promotion if any critical quality rules failed
forbid (
    principal,
    action == DataOnboarding::Action::"PassQualityGate",
    resource
)
when {
    context.guardrailCode == "DQ-002" &&
    context.criticalFailureCount > 0
};
