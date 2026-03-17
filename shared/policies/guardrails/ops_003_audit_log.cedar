// OPS-003: Forbid proceeding if audit log entry was not written
forbid (
    principal,
    action == DataOnboarding::Action::"PassOperationalCheck",
    resource
)
when {
    context.guardrailCode == "OPS-003" &&
    context.auditLogWritten == false
};
