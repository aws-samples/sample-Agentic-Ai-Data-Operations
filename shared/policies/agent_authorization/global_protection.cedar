// Protections that apply to EVERY agent principal, including the main
// conversation (onboarding). Forbid always overrides permit in Cedar.
//
// policy      — shared/policies/**: an agent must never edit the rules that
//               govern it. Policy changes are made by a human, outside any
//               agent session. Human decision 2026-10-30.
// deploy_gate — run/deploy_gate.json is written only by
//               `shared.utils.deployment_checks preflight` after a passing
//               audit; hand-writing it would bypass the audit gate.

forbid (
    principal,
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "policy" || resource.fileType == "deploy_gate"
};
