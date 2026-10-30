// INT-004: Forbid promotion if output schema does not match expected schema
forbid (
    principal,
    action == DataOnboarding::Action::"PassIntegrityCheck",
    resource
)
when {
    context.guardrailCode == "INT-004" &&
    context has schemaMatches &&
    context.schemaMatches == false
};
