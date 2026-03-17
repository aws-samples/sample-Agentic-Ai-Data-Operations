// Template: Per-workload agent access control
// Parameterize {WORKLOAD_NAME} and {AGENT_TYPE} when instantiating
//
// Example: grant the transformation agent access to the sales_transactions workload
//
// permit (
//     principal == DataOnboarding::AgentPrincipal::"transformation",
//     action == DataOnboarding::Action::"ReadData",
//     resource == DataOnboarding::DataZone::"sales_transactions_staging"
// )
// when {
//     principal.workloadName == "sales_transactions" &&
//     resource.workloadName == "sales_transactions"
// };
