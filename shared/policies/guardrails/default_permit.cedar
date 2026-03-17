// Default permit for guardrail checks.
// Cedar's default is deny-all. Guardrail policies are forbid-only rules
// that block specific failing conditions. This permit allows all guardrail
// actions by default — the forbid policies then override when checks fail.
permit (
    principal,
    action == DataOnboarding::Action::"PassSecurityCheck",
    resource
);

permit (
    principal,
    action == DataOnboarding::Action::"PassQualityGate",
    resource
);

permit (
    principal,
    action == DataOnboarding::Action::"PassIntegrityCheck",
    resource
);

permit (
    principal,
    action == DataOnboarding::Action::"PassOperationalCheck",
    resource
);
