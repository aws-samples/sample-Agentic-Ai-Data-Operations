// DQ-001: Forbid promotion if quality score is below threshold
// qualityScore and qualityThreshold are integers (score * 100)
forbid (
    principal,
    action == DataOnboarding::Action::"PassQualityGate",
    resource
)
when {
    context.guardrailCode == "DQ-001" &&
    context.qualityScore < context.qualityThreshold
};
