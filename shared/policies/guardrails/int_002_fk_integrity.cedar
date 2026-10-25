// INT-002: Forbid promotion if FK referential integrity is below threshold
// fkPassRate and fkThreshold are integers (rate * 100)
forbid (
    principal,
    action == DataOnboarding::Action::"PassIntegrityCheck",
    resource
)
when {
    context.guardrailCode == "INT-002" &&
    context.fkPassRate < context.fkThreshold
};
