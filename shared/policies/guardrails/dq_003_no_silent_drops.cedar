// DQ-003: Forbid promotion if rows were silently dropped (no quarantine record)
forbid (
    principal,
    action == DataOnboarding::Action::"PassQualityGate",
    resource
)
when {
    context.guardrailCode == "DQ-003" &&
    context.rowAccountingBalances == false
};
