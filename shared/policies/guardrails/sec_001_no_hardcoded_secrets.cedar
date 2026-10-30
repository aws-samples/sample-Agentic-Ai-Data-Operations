// SEC-001: Forbid writing a file that contains a hardcoded secret
// (AWS access keys, private keys, password/token assignments).
// secretPatternFound is computed by shared/utils/cedar_gate.py from the
// content being written, before the write happens.
forbid (
    principal,
    action == DataOnboarding::Action::"PassSecurityCheck",
    resource
)
when {
    context.guardrailCode == "SEC-001" &&
    context has secretPatternFound &&
    context.secretPatternFound == true
};
