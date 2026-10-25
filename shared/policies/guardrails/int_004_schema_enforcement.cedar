// INT-004: Forbid promotion if output schema does not match expected schema
forbid (
    principal,
    action == DataOnboarding::Action::"PassIntegrityCheck",
    resource
)
when {
    context.guardrailCode == "INT-004" &&
    context.schemaMatches == false
};
