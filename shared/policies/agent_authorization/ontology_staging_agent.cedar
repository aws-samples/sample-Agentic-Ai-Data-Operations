// Ontology Staging Agent: stages ontology.ttl, mappings.ttl and the manifest under config/, plus its tests. No AWS writes; the Semantic Layer publish agent will be a separate principal.
// Writes are an allowlist of file types; anything else is denied.

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
    resource.fileType == "config" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"WriteFile",
    resource
)
unless {
    resource.fileType == "config" || resource.fileType == "test" || resource.fileType == "decisions" || resource.fileType == "handoff"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"ReadData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"WriteData",
    resource
);

forbid (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"PromoteData",
    resource
);

// The one tool this agent is granted in its definition.
permit (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"InvokeTool",
    resource
)
when {
    resource.serverName == "glue-athena" && resource.toolName == "get_table"
};

forbid (
    principal == DataOnboarding::AgentPrincipal::"ontology_staging",
    action == DataOnboarding::Action::"InvokeTool",
    resource
)
unless {
    resource.serverName == "glue-athena" && resource.toolName == "get_table"
};
