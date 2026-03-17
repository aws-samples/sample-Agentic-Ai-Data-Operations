// OPS-004: Forbid promotion if Iceberg metadata sidecar is missing
forbid (
    principal,
    action == DataOnboarding::Action::"PassOperationalCheck",
    resource
)
when {
    context.guardrailCode == "OPS-004" &&
    context.icebergMetadataExists == false
};
