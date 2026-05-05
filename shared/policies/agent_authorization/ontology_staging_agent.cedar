// Ontology Staging Agent: reads semantic.yaml + Glue schema dict, writes
// OWL/R2RML/manifest artifacts to workloads/{name}/config/. Cannot publish,
// cannot reason, cannot touch VKG. When the AWS Semantic Layer platform deploys, a separate
// ontology-publish-agent (distinct principal) will gain the AWS write
// permissions; this principal stays read-only + file-only.

permit (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"ReadFile",
    resource
);

permit (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
when {
    resource.fileType == "config" || resource.fileType == "script"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"InvokeTool",
    resource
);
