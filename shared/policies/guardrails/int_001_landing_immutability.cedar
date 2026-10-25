// INT-001: Forbid writes to Landing zone if file already exists
forbid (
    principal,
    action == DataOnboarding::Action::"PassIntegrityCheck",
    resource
)
when {
    context.guardrailCode == "INT-001" &&
    context.landingFileWritten == false
};
