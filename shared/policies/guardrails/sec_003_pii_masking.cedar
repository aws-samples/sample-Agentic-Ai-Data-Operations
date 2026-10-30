// SEC-003: Forbid proceeding if PII columns are not masked
forbid (
    principal,
    action == DataOnboarding::Action::"PassSecurityCheck",
    resource
)
when {
    context.guardrailCode == "SEC-003" &&
    context has piiColumnsMasked &&
    context.piiColumnsMasked == false
};
