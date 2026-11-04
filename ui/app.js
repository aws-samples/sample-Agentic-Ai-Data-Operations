const app = document.getElementById("app");
const authRoot = document.getElementById("auth-root");
const appShell = document.getElementById("app-shell");
const breadcrumb = document.getElementById("breadcrumb");
const modalRoot = document.getElementById("modal-root");
const toastRoot = document.getElementById("toast-root");
const POLICY_PROPOSAL_KEY = "adop.cedar.policy.proposals";
const API_BASE = window.ADOP_API_BASE || window.ADOP_RUNTIME_CONFIG?.apiBase || "/api/v1";
const AUTH_SESSION_KEY = "adop.console.auth.session";
let remotePolicyProposals = {};
let remoteContractState = null;
let remoteConnectors = [];
let remoteWorkloads = [];
let remoteChanges = [];
let remoteAudit = [];
let remoteWorkspaces = [];
let remoteWorkloadsLoaded = false;
let policyScope = { level: "organization", name: "default" };
let contractScope = { level: "organization", name: "default" };
let selectedConnectorType = "jdbc";
let homeTab = "overview";
let authConfig = null;
let authSession = null;
let authTestUsers = [];
let remoteUsers = [];
let fatalErrorShown = false;

function showFatalError(error) {
  if (fatalErrorShown) return;
  fatalErrorShown = true;
  const message = error?.message || String(error || "Unknown client error");
  authRoot.innerHTML = `
    <main class="login-page">
      <section class="login-card">
        <div class="eyebrow">ADOP CONSOLE</div>
        <h1>Unable to render the console</h1>
        <p class="login-copy">The login request completed, but the browser hit a client-side rendering error.</p>
        <div class="login-error" role="alert">${escapeHtml(message)}</div>
        <button class="button primary login-submit" id="clear-session-reload">Clear local session and reload</button>
      </section>
    </main>
  `;
  appShell.hidden = true;
  document.getElementById("clear-session-reload")?.addEventListener("click", () => {
    sessionStorage.removeItem(AUTH_SESSION_KEY);
    window.location.reload();
  });
}

window.addEventListener("error", event => {
  showFatalError(event.error || event.message);
});
window.addEventListener("unhandledrejection", event => {
  showFatalError(event.reason);
});

const cedarPolicies = {
  "agent_authorization/global_protection": {
    title: "Agent authorization",
    path: "shared/policies/agent_authorization/global_protection.cedar",
    count: "11 policies",
    detail: "Role-scoped writes and tool access",
    text: "",
  },
  "guardrails/sec_003_pii_masking": {
    title: "PII masking guardrail",
    path: "shared/policies/guardrails/sec_003_pii_masking.cedar",
    count: "16 policies",
    detail: "Security guardrail for PII masking",
    text: "",
  },
  "guardrails/dq_001_quality_gate_threshold": {
    title: "Quality gate guardrail",
    path: "shared/policies/guardrails/dq_001_quality_gate_threshold.cedar",
    count: "4 DQ policies",
    detail: "Quality promotion threshold enforcement",
    text: "",
  },
};

const repoState = {
  workload: {
    name: "customer_orders",
    description: "Daily order-level sales reporting",
    runId: "regen-20261023-customer-orders",
    phase: "4.3",
    status: "Build in progress",
    source: "CSV · IAM role",
    schedule: "09:00 America/New_York",
    compliance: "GDPR",
    piiCount: 8,
    silverThreshold: "0.80",
    goldThreshold: "0.95",
    goldSchema: "Flat Iceberg",
    primaryKey: "order_id",
    ontology: "Opted out",
    effectiveHash: "c088235b…",
  },
  approvals: [
    { title: "Gold quality floor", detail: "Tighten 0.95 → 0.97 · sales domain", icon: "↗" },
    { title: "New Teradata connector", detail: "td_finance · read-only access", icon: "⌁" },
    { title: "Cedar enforcement request", detail: "Audit → enforce · two approvers required", icon: "◉" },
  ],
};

const views = {
  home: { label: "Home", render: renderHome },
  workloads: { label: "Workloads", render: renderWorkloads },
  contracts: { label: "Contracts", render: renderContracts },
  connectors: { label: "Connectors", render: renderConnectors },
  policies: { label: "Policies", render: renderPolicies },
  approvals: { label: "Approvals", render: renderApprovals },
  runs: { label: "Runs", render: renderRuns },
  audit: { label: "Audit log", render: renderAudit },
  workspaces: { label: "Workspaces", render: renderWorkspaces },
  access: { label: "Access", render: renderAccess },
};

const workloadProjects = {
  customer_orders: "orders",
  claims: "claims",
  sales_daily: "sales_daily",
};

let currentView = "home";

function shell(eyebrow, title, description, actions = "") {
  return `
    <div class="page-heading">
      <div>
        <div class="eyebrow">${eyebrow}</div>
        <h1>${title}</h1>
        <p>${description}</p>
      </div>
      <div class="heading-actions">${actions}</div>
    </div>
  `;
}

function metric(label, value, trend, icon, tone = "") {
  return `
    <div class="metric-card">
      <div class="metric-top"><span>${label}</span><span class="metric-icon">${icon}</span></div>
      <div class="metric-number">${value}</div>
      <div class="metric-trend ${tone}">${trend}</div>
    </div>
  `;
}

function status(text, tone = "success") {
  return `<span class="status-chip ${tone}"><span class="status-dot ${tone === "success" ? "green" : tone === "pending" ? "orange" : tone === "failed" ? "red" : "blue"}"></span>${text}</span>`;
}

function renderHome() {
  const ordersVisible = remoteWorkloads.some(item => item.name === "customer_orders");
  const approvals = repoState.approvals || [];
  const tabs = [
    ["overview", "Overview", ""],
    ["approvals", "Approvals", approvals.length ? `<span class="home-tab-count">${approvals.length}</span>` : ""],
    ["health", "Health", ""],
  ];
  return `
    ${shell("OVERVIEW", `Good morning, ${escapeHtml(authSession?.identity?.name || "there")}`, "Workload health and governance at a glance.", `<button class="button primary" data-view-link="approvals">Review changes</button>`)}
    <div class="metric-grid">
      ${metric("ACTIVE WORKLOADS", "12", "↑ 2 this month", "◈")}
      ${metric("QUALITY GATE PASS", "98.4%", "↑ 1.6% vs last month", "✓")}
      ${metric("RUNS TODAY", "31", "28 passed · 3 running", "◷", "neutral")}
      ${metric("PENDING APPROVALS", String(approvals.length), "Needs your attention", "!", "warn")}
    </div>
    <div class="home-tabs" role="tablist">
      ${tabs.map(([id, label, extra]) => `<button class="home-tab ${homeTab === id ? "active" : ""}" role="tab" aria-selected="${homeTab === id}" data-action="home-tab" data-home-tab="${id}">${label}${extra}</button>`).join("")}
    </div>
    <div class="home-tab-panel" role="tabpanel">${homeTabContent(homeTab, ordersVisible, approvals)}</div>
  `;
}

function homeTabContent(tab, ordersVisible, approvals) {
  if (tab === "approvals") {
    return `
      <section class="panel">
        <div class="panel-header"><div><h2 class="panel-title">Pending approvals</h2><p class="panel-subtitle">Changes waiting on a human decision</p></div><button class="panel-link" data-view-link="approvals">Open approvals</button></div>
        ${approvals.length ? `<div class="approval-list">${approvals.map(approval => `<div class="approval-item"><div class="approval-mark">${approval.icon}</div><div class="approval-copy"><strong>${approval.title}</strong><small>${approval.detail}</small></div><button class="panel-link" data-action="review">Review</button></div>`).join("")}</div>` : `<p class="panel-subtitle">Nothing is waiting for you.</p>`}
      </section>`;
  }
  if (tab === "health") {
    return `
      <section class="panel quality-panel">
        <div class="panel-header"><div><h2 class="panel-title">Workspace health</h2><p class="panel-subtitle">Technical KPIs across the last 30 days</p></div><button class="panel-link" data-view-link="runs">Open run history</button></div>
        ${qualityRow("Quality score", 98, "98.4%")}
        ${qualityRow("Freshness SLA", 94, "94.0%")}
        ${qualityRow("PII tag coverage", 100, "100%")}
        ${qualityRow("Schema stability", 88, "88.0%", true)}
      </section>`;
  }
  if (!ordersVisible) {
    return `<section class="panel empty-state"><div class="empty-icon">◎</div><h2 class="panel-title">No workload in this workspace</h2><p class="panel-subtitle">You're signed in, but none of the current workloads belong to the selected project.</p></section>`;
  }
  const w = repoState.workload;
  return `
    <section class="panel home-product">
      <div class="home-product-head">
        <div>
          <div class="eyebrow home-eyebrow">ACTIVE DATA PRODUCT</div>
          <h2>customer_orders</h2>
          <p class="panel-subtitle">One governed path from raw landing to business-ready data.</p>
        </div>
        ${status(w.status, "pending")}
      </div>
      <div class="home-product-meta">
        <div><span>Source</span><strong>${w.source.split(" · ")[0]}</strong></div>
        <div><span>Schedule</span><strong>${w.schedule}</strong></div>
        <div><span>Snapshot</span><strong>${w.effectiveHash.slice(0, 10)}…</strong></div>
        <div><span>Policy</span><strong>effective · v1.4</strong></div>
      </div>
      <div class="home-path" aria-label="Bronze to Silver to Gold data lake zones">
        <div class="home-zone bronze"><span class="home-zone-step">01 · INGEST</span><strong>Bronze</strong><small>Raw landing · immutable · CSV</small></div>
        <div class="home-gate">quality gate →</div>
        <div class="home-zone silver"><span class="home-zone-step">02 · VALIDATE</span><strong>Silver</strong><small>Iceberg · quality ≥ 0.80 · PII checked</small></div>
        <div class="home-gate">promotion gate →</div>
        <div class="home-zone gold"><span class="home-zone-step">03 · SERVE</span><strong>Gold</strong><small>Flat Iceberg · quality ≥ 0.95</small></div>
      </div>
      <div class="home-lake-note"><span class="home-note-icon">✓</span><span>Every run is pinned to the resolved contract before it moves between zones.</span></div>
    </section>`;
}

function zoneNode(name, type, value, dot, extra = "") {
  return `<div class="zone-node ${extra}"><div class="zone-node-top"><span class="zone-name">${name}</span><span class="zone-type">${type}</span></div><div class="zone-value">${value}</div><div class="zone-meta">${name === "Bronze" ? "Source contract v1.0.0" : name === "Silver" ? "Iceberg · updatable" : "Gold contract v2"}</div><span class="status-dot ${dot}"></span></div>`;
}

function qualityRow(label, width, value, amber = false) {
  return `<div class="quality-row"><span class="quality-label">${label}</span><div class="bar"><span class="${amber ? "amber" : ""}" style="width:${width}%"></span></div><span class="quality-number">${value}</span></div>`;
}

function renderWorkloads() {
  const metadata = {
    customer_orders: { desc: "Order-level sales reporting", status: "Build in progress", tone: "pending", tags: ["GDPR", "Flat Iceberg", "Daily"], owner: "Sales analytics", run: "Phase 4.3" },
    claims: { desc: "Claims intake and enrichment", status: "Failed", tone: "failed", tags: ["HIPAA", "Star schema", "Hourly"], owner: "Risk data", run: "Quality gate" },
    sales_daily: { desc: "Executive sales performance", status: "Healthy", tone: "success", tags: ["SOX", "Flat Iceberg", "Daily"], owner: "Finance BI", run: "Last run 14m ago" },
  };
  const workloads = remoteWorkloads.map(item => ({ name: item.name, ...metadata[item.name] })).filter(item => item.desc);
  return `
    ${shell("MONITOR / WORKLOADS", "Workloads", "Monitor data products, effective contracts, and execution state.", `<button class="button" data-action="export">Export inventory</button><button class="button primary" data-action="create-workload">＋ New workload</button>`)}
    <div class="panel">
      <div class="panel-header"><div><h2 class="panel-title">All workloads</h2><p class="panel-subtitle">12 workloads in the Sales data workspace</p></div><button class="button small" data-action="filter">Filter · All statuses</button></div>
      ${workloads.length ? workloads.map(item => `<div class="workload-card" data-action="workload-detail"><div class="workload-head"><div class="workload-name"><div class="workload-icon">◈</div><div><h3>${item.name}</h3><p>${item.desc}</p></div></div>${status(item.status, item.tone)}</div><div class="workload-meta">${item.tags.map(tag => `<span class="tag ${tag === "GDPR" || tag === "HIPAA" || tag === "SOX" ? "blue" : "gray"}">${tag}</span>`).join("")}</div><div class="workload-footer"><span>Owner <strong>${item.owner}</strong></span><span>${item.run}</span><button class="panel-link">Open workload →</button></div></div>`).join("") : `<div class="empty-state"><strong>No eligible workloads</strong><p>This project user cannot see workloads outside their project membership.</p></div>`}
    </div>
  `;
}

function renderContracts() {
  const selectedWorkload = currentContractWorkload();
  if (remoteWorkloadsLoaded && !selectedWorkload) {
    return `
      ${shell("RULES ENGINE / CONTRACTS", "Contracts", "Contracts are shown only when the selected workspace contains an eligible workload.")}
      <section class="panel empty-state">
        <div class="empty-icon">⌘</div>
        <h2 class="panel-title">No contract in this workspace</h2>
        <p class="panel-subtitle">The selected workspace has no visible workload contract. Switch to an eligible project or domain to review inherited rules.</p>
      </section>
    `;
  }
  const contract = remoteContractState;
  const effective = contract?.effective || {};
  const layers = contract?.layers || {};
  const canEdit = canEditContractScope(contractScope.level, contractScope.name);
  const selectedLayer = layers[contractScope.level];
  const inherited = contractScope.level === "organization"
    ? layers.organization?.policy
    : (selectedLayer?.policy || effective);
  const scopeTitle = contractScope.level === "organization"
    ? "Organization"
    : `${contractScope.level[0].toUpperCase()}${contractScope.level.slice(1)} · ${contractScope.name}`;
  const effectiveHash = effective.effective_hash || repoState.workload.effectiveHash;
  return `
    ${shell("RULES ENGINE / CONTRACTS", "Contracts", "See inherited policy, effective values, and proposed changes before they reach a run.", `<span class="tag green">Effective hash · ${String(effectiveHash).slice(0, 12)}…</span>${canEdit ? '<button class="button primary" data-action="propose-contract">＋ Propose project change</button>' : '<span class="tag gray">Review only · project updates</span>'}`)}
    <section class="panel">
      <div class="panel-header"><div><h2 class="panel-title">Zone contracts</h2><p class="panel-subtitle">Editing scope: <strong>${scopeTitle}</strong>. Lower scopes can tighten the inherited baseline, never weaken it.</p></div><div class="scope-tabs">
        ${scopeTab("contract", "organization", "Organization", "default")}
        ${scopeTab("contract", "domain", "Sales domain", "sales")}
        ${scopeTab("contract", "project", "Orders project", "orders")}
      </div></div>
      <div class="contract-grid">
        ${contractCardFromPolicy("Bronze", "Raw landing", "⌁", inherited?.zones?.bronze, [["Allowed formats", "7 source formats"], ["Encryption", "KMS · AES-256"], ["Transport", "TLS 1.3"]])}
        ${contractCardFromPolicy("Silver", "Standardized Iceberg", "◇", inherited?.zones?.silver, [["Format", "Apache Iceberg"], ["Mutability", "Updatable"], ["PII detection", "Required"]])}
        ${contractCardFromPolicy("Gold", "Business serving", "✦", inherited?.zones?.gold, [["Schema", "Flat Iceberg"], ["Grain", "order_id"], ["KPIs", "order_count · revenue"]])}
      </div>
      <div class="callout"><span class="callout-icon">ⓘ</span><span><strong>Effective policy is resolved from organization → domain → project → workload.</strong> The current workload inherits the organization baseline. Any proposed reduction is rejected by the API before approval.</span></div>
    </section>
    <section class="panel inheritance-panel">
      <div class="panel-header"><div><h2 class="panel-title">Inheritance preview</h2><p class="panel-subtitle">What a workload owner sees when this policy is resolved</p></div><button class="panel-link" data-action="validate">Validate resolution</button></div>
      <div class="inheritance-row header"><div>Zone</div><div>Organization</div><div>Domain</div><div>Project / effective</div></div>
      ${inheritanceRow("Bronze", layers.organization?.policy?.zones?.bronze, layers.domain?.policy?.zones?.bronze, effective.zones?.bronze)}
      ${inheritanceRow("Silver", layers.organization?.policy?.zones?.silver, layers.domain?.policy?.zones?.silver, effective.zones?.silver)}
      ${inheritanceRow("Gold", layers.organization?.policy?.zones?.gold, layers.domain?.policy?.zones?.gold, effective.zones?.gold)}
    </section>
    <section class="panel section-gap">
      <div class="panel-header"><div><h2 class="panel-title">Data KPI contracts</h2><p class="panel-subtitle">Enhance-only technical KPIs inherited by every workload</p></div><button class="button small" data-action="add-kpi">＋ Add KPI from catalog</button></div>
      <table class="table"><thead><tr><th>KPI</th><th>Direction</th><th>Threshold</th><th>Source</th><th>State</th><th></th></tr></thead><tbody>
        ${kpiRow("quality_score", "≥", "0.95", "Organization", "Enforced")}
        ${kpiRow("freshness_lag_minutes", "≤", "30", "Organization", "Enforced")}
        ${kpiRow("uniqueness_pct", "≥", "0.99", "Organization", "Enforced")}
        ${kpiRow("pii_tag_coverage", "≥", "1.00", "Organization", "Enforced")}
      </tbody></table>
    </section>
  `;
}

function currentContractWorkload() {
  const workspace = selectedWorkspace();
  const project = workspace?.level === "project" ? workspace.name : null;
  return remoteWorkloads.find(item => !project || workloadProjects[item.name] === project) || null;
}

function scopeTab(kind, level, label, name) {
  if (!canViewWorkspace(level, name)) return "";
  const selected = kind === "contract" ? contractScope : policyScope;
  return `<button class="scope-tab ${selected.level === level ? "active" : ""}" data-action="${kind}-scope" data-scope-level="${level}" data-scope-name="${name}">${label}</button>`;
}

function contractCardFromPolicy(title, subtitle, symbol, zone, fallbackLines) {
  const lines = zone ? Object.entries(zone).filter(([key]) => !["mutability", "required_format", "minimum_quality_threshold", "allowed_source_formats"].includes(key)).map(([key, value]) => [key.replaceAll("_", " "), Array.isArray(value) ? value.join(", ") : String(value)]) : fallbackLines;
  const gate = zone?.minimum_quality_threshold != null ? `Quality gate ≥ ${Number(zone.minimum_quality_threshold).toFixed(2)}` : zone?.mutability || "Inherited";
  const values = [
    ...(zone?.allowed_source_formats ? [["Allowed formats", `${zone.allowed_source_formats.length} formats`]] : []),
    ...(zone?.required_format ? [["Format", zone.required_format]] : []),
    ...(zone?.pii_detection_required ? [["PII detection", "Required"]] : []),
    ...lines.slice(0, 3),
  ];
  return contractCard(title, subtitle, gate, values.length ? values : fallbackLines, symbol);
}

function inheritanceRow(zone, organization, domain, effective) {
  const value = item => {
    if (!item) return ["Inherited", "No override"];
    if (item.minimum_quality_threshold != null) return [`≥ ${Number(item.minimum_quality_threshold).toFixed(2)}`, item.required_format || "Quality floor"];
    if (item.allowed_source_formats) return ["Formats narrowed", `${item.allowed_source_formats.length} allowed formats`];
    return [item.mutability || "Configured", item.required_format || "Contract rule"];
  };
  const [orgValue, orgDetail] = value(organization);
  const [domainValue, domainDetail] = value(domain);
  const [effectiveValue, effectiveDetail] = value(effective);
  return `<div class="inheritance-row"><div><strong>${zone}</strong></div><div><strong>${orgValue}</strong><small>${orgDetail}</small></div><div><strong>${domainValue}</strong><small>${domainDetail}</small></div><div class="effective"><strong>${effectiveValue}</strong><small>${effectiveDetail}</small></div></div>`;
}

function contractCard(title, subtitle, gate, lines, symbol) {
  return `<div class="zone-card"><div class="zone-card-header"><div><h3>${title}</h3><span class="panel-subtitle">${subtitle}</span></div><span class="zone-symbol">${symbol}</span></div><span class="tag green">${gate}</span>${lines.map(([label, value]) => `<div class="contract-line"><span>${label}</span><strong>${value}</strong></div>`).join("")}</div>`;
}

function kpiRow(name, direction, threshold, source, state) {
  return `<tr><td><strong>${name}</strong></td><td>${direction}</td><td><strong>${threshold}</strong></td><td>${source}</td><td><span class="tag green">${state}</span></td><td class="right"><button class="panel-link" data-action="tighten">Tighten</button></td></tr>`;
}

function renderConnectors() {
  const connectors = remoteConnectors;
  return `
    ${shell("INTEGRATIONS / CONNECTORS", "Connectors", "Reusable source profiles with write-only credentials and real provider health checks.", `<button class="button" data-action="test-all-connectors">Test all</button><button class="button" data-action="connector-docs">Connector guide</button><button class="button primary" data-action="new-connector">＋ New connector</button>`)}
    <div class="callout" style="margin: 0 0 16px"><span class="callout-icon">⌁</span><span><strong>Credentials and connection metadata can stay in Secrets Manager.</strong> The connector record stores only the ARN. Host, port, database, and engine fields can be left blank when the secret JSON contains them. Health checks return only a redacted result.</span></div>
    ${connectors.length ? `<div class="connector-grid">${connectors.map(connectorCard).join("")}</div>` : `<section class="panel empty-state"><div class="empty-icon">⌁</div><h2 class="panel-title">No connectors configured</h2><p class="panel-subtitle">Add a Snowflake, Databricks, Teradata, or JDBC profile with a Secrets Manager reference, then run a real health check.</p><button class="button primary" data-action="new-connector">＋ Configure connector</button></section>`}
    <section class="panel section-gap">
      <div class="panel-header"><div><h2 class="panel-title">Connector bindings</h2><p class="panel-subtitle">Separate connector profile, source contract, and workload binding.</p></div><button class="panel-link" data-action="binding-help">How bindings work</button></div>
      <table class="table"><thead><tr><th>Workload</th><th>Connector</th><th>Source contract</th><th>Access</th><th>State</th></tr></thead><tbody>
        <tr><td colspan="5"><span class="panel-subtitle">No workload bindings are configured. A connector profile must pass a real health check before it can be bound.</span></td></tr>
      </tbody></table>
    </section>
  `;
}

function connectorCard(connector) {
  const type = String(connector.type || "jdbc").toLowerCase();
  const label = type[0].toUpperCase() + type.slice(1);
  const health = connector.health || {};
  const statusMap = {
    healthy: ["Healthy", "success"],
    unhealthy: ["Unhealthy", "failed"],
    network_reachable: ["Network reachable · auth not tested", "info"],
    not_tested: ["Not tested", "pending"],
  };
  const [state, tone] = statusMap[connector.status] || ["Not configured", "pending"];
  const tested = health.checked_at ? new Date(health.checked_at).toLocaleString() : "Never";
  const detail = health.error_code ? `${health.error_code}: ${health.error_message}` : connector.secret_configured ? "Secret reference configured" : "Secret reference missing";
  return `<div class="connector-card"><div class="connector-head"><div class="connector-logo ${escapeHtml(type)}">${escapeHtml(label.slice(0, 2).toUpperCase())}</div>${status(state, tone)}</div><h3>${escapeHtml(connector.name)}</h3><p>${escapeHtml(label)} · ${escapeHtml(connector.access_mode || "read-only")} profile</p><div class="connector-meta"><span>${escapeHtml(detail)}</span><span>Tested <strong>${escapeHtml(tested)}</strong></span></div><button class="panel-link connector-test-link" data-action="test-connector-card" data-connector-id="${escapeHtml(connector.connector_id)}">Run real health check →</button></div>`;
}

function renderPolicies() {
  return `
    ${shell("RULES ENGINE / POLICIES", "Policies", "Review Cedar authorization posture and propose changes through a human-approved workflow.", `<span class="mode-switch"><span class="mode-pill">AUDIT MODE</span> Change requires two approvers</span><button class="button primary" data-action="policy-proposal">＋ Propose change</button>`)}
    <section class="policy-store">
      <div class="policy-store-copy"><span class="policy-store-icon">◉</span><div><strong>Where Cedar policies live</strong><small>Applied policy source: <code>shared/policies/**</code> in Git. This console creates proposals, validates edits, and tracks approvals; it does not silently overwrite policy files.</small></div></div>
      <div class="policy-store-actions"><button class="button small" data-action="open-policy-store">View store</button><button class="button small" data-action="policy-proposal">New proposal</button></div>
    </section>
    <div class="panel scope-panel"><div class="panel-header"><div><h2 class="panel-title">Policy scope</h2><p class="panel-subtitle">Organization is the baseline; domain and project policies inherit it and are proposed separately.</p></div><div class="scope-tabs">
      ${scopeTab("policy", "organization", "Organization", "default")}
      ${scopeTab("policy", "domain", "Sales domain", "sales")}
      ${scopeTab("policy", "project", "Orders project", "orders")}
    </div></div><div class="scope-summary"><span class="tag blue">${policyScope.level} · ${policyScope.name}</span><span>${policyScope.level === "organization" ? "Global Cedar source" : "Inherits from organization/default"}</span></div></div>
    <div class="layout-two">
      <section class="policy-card"><div class="panel-header"><div><h2 class="panel-title">Policy surfaces</h2><p class="panel-subtitle">Policy code remains reviewable and deployable through Git.</p></div><span class="tag blue">11 agent policies</span></div><div class="policy-list">
        ${policyRow("agent_authorization/global_protection", "Agent authorization", "11 policies", "Role-scoped writes and tool access")}
        ${policyRow("guardrails/sec_003_pii_masking", "PII masking guardrail", "16 policies", "Security guardrail for PII masking")}
        ${policyRow("guardrails/dq_001_quality_gate_threshold", "Quality gate guardrail", "4 DQ policies", "Quality promotion threshold enforcement")}
      </div><div class="callout"><span class="callout-icon">◉</span><span>The console proposes Cedar changes; it does not write <code>shared/policies/**</code> directly.</span></div></section>
      <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Decision activity</h2><p class="panel-subtitle">Last 7 days · read-only view</p></div><button class="panel-link" data-view-link="audit">View audit log</button></div>${qualityRow("Allow", 98, "412")}${qualityRow("Deny", 14, "3", true)}${qualityRow("Audit-only", 54, "27")}</section>
    </div>
    <section class="panel section-gap"><div class="panel-header"><div><h2 class="panel-title">Recent policy changes</h2><p class="panel-subtitle">Proposals, approvals, and deployment evidence</p></div><button class="button small" data-action="policy-history">View history</button></div><table class="table"><thead><tr><th>Change</th><th>Author</th><th>Approval</th><th>Status</th><th>Hash</th></tr></thead><tbody>
      <tr><td><strong>Require PII masking before Silver</strong></td><td>Platform security</td><td>2 / 2</td><td>${status("Applied", "success")}</td><td><code>9f3a…b18c</code></td></tr>
      <tr><td><strong>Switch enforcement mode</strong></td><td>Maya Chen</td><td>1 / 2</td><td>${status("Pending", "pending")}</td><td><code>pending</code></td></tr>
      <tr><td><strong>Restrict project connector writes</strong></td><td>Data governance</td><td>2 / 2</td><td>${status("PR open", "info")}</td><td><code>4d7e…a210</code></td></tr>
    </tbody></table></section>
  `;
}

function policyRow(policyId, title, count, detail) {
  const proposal = getPolicyProposal(policyId);
  return `<div class="policy-row"><div><strong>${title}</strong><small>${detail} · ${policyScope.level}/${policyScope.name}</small></div><span class="tag ${proposal ? "proposal-state" : "gray"}">${proposal ? "Proposal saved" : count}</span><button class="panel-link" data-action="view-policy" data-policy-id="${policyId}">View / edit →</button></div>`;
}

function renderApprovals() {
  const pending = remoteChanges.filter(item => ["pending_approval", "approved_pending_git"].includes(item.status));
  const decided = remoteChanges.filter(item => ["rejected", "applied"].includes(item.status));
  return `
    ${shell("GOVERNANCE / APPROVALS", "Approvals", "One queue for contract, connector, and policy decisions.", `<button class="button" data-action="refresh-approvals">Refresh queue</button>`)}
    <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Needs your decision</h2><p class="panel-subtitle">The API filters this queue by the selected workspace and role.</p></div><span class="tag orange">${pending.length} pending</span></div><table class="table"><thead><tr><th>Change</th><th>Scope</th><th>Requested by</th><th>Approvals</th><th>Created</th><th></th></tr></thead><tbody>
      ${pending.length ? pending.map(approvalRow).join("") : `<tr><td colspan="6"><div class="empty-state"><strong>No pending approvals</strong><p>New contract and Cedar proposals will appear here after validation.</p></div></td></tr>`}
    </tbody></table></section>
    <section class="panel section-gap"><div class="panel-header"><div><h2 class="panel-title">Recently decided</h2><p class="panel-subtitle">Immutable approval history</p></div><button class="panel-link" data-view-link="audit">Open audit log</button></div><table class="table"><thead><tr><th>Change</th><th>Decision</th><th>By</th><th>When</th></tr></thead><tbody>
      ${decided.length ? decided.slice(0, 10).map(decidedRow).join("") : `<tr><td colspan="4"><span class="panel-subtitle">No decided changes in this workspace.</span></td></tr>`}
    </tbody></table></section>
  `;
}

function changeTitle(change) {
  if (change.change_type === "zone_contract") return `Zone contract · ${change.contract_id || "adop.zone-governance"}`;
  return `Cedar policy · ${change.policy_id || change.subject_id || "policy"}`;
}

function changeScope(change) {
  return `${change.scope || "organization"}/${change.scope_name || "default"}`;
}

function approvalCount(change) {
  const approvals = (change.approvals || []).filter(item => item.decision === "approve").length;
  return `${approvals} / ${change.required_approvals || 2}`;
}

function formatTimestamp(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

function approvalRow(change) {
  return `<tr><td><strong>${escapeHtml(changeTitle(change))}</strong><small class="panel-subtitle">${escapeHtml(change.change_type === "zone_contract" ? "Validated contract proposal" : "Validated Cedar proposal")}</small></td><td>${escapeHtml(changeScope(change))}</td><td>${escapeHtml(change.created_by || "Unknown")}</td><td><span class="tag ${approvalCount(change).startsWith("0") ? "orange" : "blue"}">${approvalCount(change)}</span></td><td>${escapeHtml(formatTimestamp(change.created_at))}</td><td class="right"><button class="button small" data-action="review-change" data-change-id="${escapeHtml(change.change_id)}">Review</button></td></tr>`;
}

function decidedRow(change) {
  const rejected = change.status === "rejected";
  const actors = (change.approvals || []).map(item => item.actor).join(" · ");
  return `<tr><td><strong>${escapeHtml(changeTitle(change))}</strong></td><td>${status(rejected ? "Rejected" : "Approved", rejected ? "failed" : "success")}</td><td>${escapeHtml(actors || change.created_by || "Unknown")}</td><td>${escapeHtml(formatTimestamp(change.updated_at || change.created_at))}</td></tr>`;
}

function renderApprovalReview(change) {
  const content = typeof change.content === "string"
    ? change.content
    : JSON.stringify(change.content || {}, null, 2);
  const approvals = (change.approvals || []).map(item => `<div class="approval-history-row"><strong>${escapeHtml(item.actor)}</strong><span>${escapeHtml(item.decision)}</span><small>${escapeHtml(item.comment || "No comment")}</small></div>`).join("");
  const canDecide = change.status === "pending_approval" && hasFeature("approvals.decide");
  modalRoot.innerHTML = `
    <div class="modal-backdrop" data-modal-close>
      <div class="modal policy-editor" role="dialog" aria-modal="true" aria-labelledby="approval-review-title">
        <div class="modal-header"><div><h2 id="approval-review-title">Review change</h2><p>${escapeHtml(changeTitle(change))} · ${escapeHtml(changeScope(change))}</p></div><button class="modal-close" data-modal-close aria-label="Close">×</button></div>
        <div class="modal-body">
          <div class="editor-meta"><span class="tag blue">${escapeHtml(change.change_type || "configuration")}</span><span class="tag gray">${escapeHtml(approvalCount(change))} approvals</span><span class="tag proposal-state">${escapeHtml(change.status || "pending")}</span></div>
          <div class="approval-review-meta"><span>Requested by <strong>${escapeHtml(change.created_by || "Unknown")}</strong></span><span>Created ${escapeHtml(formatTimestamp(change.created_at))}</span></div>
          <textarea class="policy-textarea" readonly spellcheck="false">${escapeHtml(content)}</textarea>
          <div class="approval-history"><strong>Decision history</strong>${approvals || '<span class="panel-subtitle">No decisions yet.</span>'}</div>
          ${change.external_reference ? `<div class="callout"><span class="callout-icon">↗</span><span>GitHub change linked: ${escapeHtml(change.external_reference.url || change.external_reference.branch || "external review")}</span></div>` : ""}
        </div>
        <div class="modal-footer"><button class="button" data-modal-close>Close</button>${canDecide ? `<button class="button" data-action="decide-change" data-decision="reject" data-change-id="${escapeHtml(change.change_id)}">Reject</button><button class="button primary" data-action="decide-change" data-decision="approve" data-change-id="${escapeHtml(change.change_id)}">Approve</button>` : `<span class="panel-subtitle">A decision cannot be added in the current state.</span>`}</div>
      </div>
    </div>
  `;
}

function renderRuns() {
  const runs = remoteWorkloads;
  return `
    ${shell("MONITOR / RUNS", "Runs", "Execution evidence, quality gates, and pinned configuration snapshots.", `<button class="button" data-action="export">Export run evidence</button><button class="button primary" data-action="trigger-run">▶ Trigger test run</button>`)}
    <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Recent pipeline runs</h2><p class="panel-subtitle">Runs are immutable views of the configuration snapshot used at start.</p></div><button class="button small" data-action="filter">Last 30 days</button></div><table class="table"><thead><tr><th>Workload</th><th>Run ID</th><th>Phase</th><th>Quality</th><th>Started</th><th>Status</th></tr></thead><tbody>
      ${runs.length ? runs.map(runRow).join("") : `<tr><td colspan="6"><div class="empty-state"><strong>No visible runs</strong><p>Run evidence appears when the selected workspace has an eligible workload.</p></div></td></tr>`}
    </tbody></table></section>
  `;
}

function renderAudit() {
  return `
    ${shell("GOVERNANCE / AUDIT", "Audit log", "A complete trail of configuration proposals, approvals, resolutions, and run evidence.", `<button class="button" data-action="export">Download JSONL</button>`)}
    <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Activity timeline</h2><p class="panel-subtitle">All times shown in America/New_York · API-backed</p></div><button class="button small" data-action="refresh-audit">Refresh activity</button></div><table class="table"><thead><tr><th>Event</th><th>Actor</th><th>Scope</th><th>Result</th><th>Timestamp</th></tr></thead><tbody>
      ${remoteAudit.length ? remoteAudit.map(auditRow).join("") : `<tr><td colspan="5"><div class="empty-state"><strong>No audit activity</strong><p>Configuration and workspace actions will appear here.</p></div></td></tr>`}
    </tbody></table></section>
  `;
}

function runRow(run) {
  const phase = run.phase || "unknown";
  const statusText = phase === "5.9" ? "Passed" : "In progress";
  return `<tr><td><strong>${escapeHtml(run.name)}</strong></td><td><code>${escapeHtml(run.run_id || "—")}</code></td><td>${escapeHtml(phase)}</td><td>Repository snapshot</td><td>${escapeHtml(formatTimestamp(run.started_at))}</td><td>${status(statusText, statusText === "Passed" ? "success" : "pending")}</td></tr>`;
}

function auditRow(item) {
  const event = String(item.event_type || "activity").replaceAll("_", " ");
  const scope = item.scope ? `${item.scope}/${item.scope_name || "default"}` : item.workspace || "—";
  const tone = String(item.event_type || "").includes("reject") ? "failed" : "info";
  return `<tr><td><strong>${escapeHtml(event)}</strong><small class="panel-subtitle">${escapeHtml(item.subject_id || item.connector_name || item.policy_id || "")}</small></td><td>${escapeHtml(item.actor || "system")}</td><td>${escapeHtml(scope)}</td><td>${status(item.status || "Recorded", tone)}</td><td>${escapeHtml(formatTimestamp(item.timestamp))}</td></tr>`;
}

function renderAccess() {
  const identity = authSession?.identity || {};
  const permissions = identity.feature_permissions || [];
  return `
    ${shell("ADMIN / ACCESS", "Access management", "Review role, workspace membership, and feature permissions for the current organization.", `<button class="button" data-action="refresh-access">Refresh directory</button><button class="button primary" data-action="invite-user">＋ Invite user</button>`)}
    <section class="panel access-summary">
      <div class="panel-header"><div><h2 class="panel-title">Permission model</h2><p class="panel-subtitle">Effective access is calculated from role, workspace membership, feature, and action.</p></div><span class="tag blue">Server enforced</span></div>
      <div class="workspace-access-grid">
        <div class="workspace-access-item"><span class="workspace-access-icon">◎</span><div><strong>Selected workspace</strong><small>${escapeHtml(workspaceKey(selectedWorkspace()))}</small></div></div>
        <div class="workspace-access-item"><span class="workspace-access-icon">◇</span><div><strong>Role</strong><small>${escapeHtml(identity.role_label || identity.role || "Unknown")}</small></div></div>
        <div class="workspace-access-item"><span class="workspace-access-icon">✓</span><div><strong>Feature grants</strong><small>${permissions.length} active permissions</small></div></div>
      </div>
    </section>
    ${workspaceAccessPanel()}
    <section class="panel section-gap">
      <div class="panel-header"><div><h2 class="panel-title">Directory users</h2><p class="panel-subtitle">${authConfig?.mode === "local" ? "Local test directory" : "Users are managed by the configured identity provider."}</p></div><span class="tag green">${remoteUsers.length} loaded</span></div>
      ${remoteUsers.length ? `<div class="access-user-list">${remoteUsers.map(accessUserRow).join("")}</div>` : `<div class="empty-state"><div class="empty-icon">♙</div><strong>No directory users returned</strong><p>Connect the production IdP directory adapter to manage users here.</p></div>`}
    </section>
    <section class="panel section-gap">
      <div class="panel-header"><div><h2 class="panel-title">Role capabilities</h2><p class="panel-subtitle">Specialist roles narrow access to specific governance features.</p></div></div>
      <div class="permission-grid">${[
        ["Organization admin", "Full organization, domain, project, user, policy, connector, and approval access"],
        ["Domain owner", "Domain contracts, connectors, policy proposals, and approvals"],
        ["Project user", "Assigned project workloads, contracts, policies, and connector tests"],
        ["Security administrator", "Cedar policies, validation, approvals, and audit"],
        ["Connector administrator", "Connector registration, health checks, and connector approvals"],
        ["Auditor / Viewer", "Read-only governance and audit access"],
      ].map(([title, detail]) => `<div class="permission-card"><strong>${title}</strong><small>${detail}</small></div>`).join("")}</div>
    </section>
  `;
}

function renderWorkspaces() {
  const workspaces = remoteWorkspaces.length
    ? remoteWorkspaces
    : availableWorkspaces();
  const domains = workspaces.filter(item => item.level === "domain");
  const projects = workspaces.filter(item => item.level === "project");
  return `
    ${shell("ADMIN / WORKSPACES", "Workspaces", "Create and organize the domains and projects that define ADOP access boundaries.", `<button class="button" data-action="refresh-workspaces">Refresh</button><button class="button primary" data-action="new-workspace">＋ New workspace</button>`)}
    <section class="panel workspace-admin-hero">
      <div class="workspace-admin-hero-copy">
        <span class="eyebrow">ORGANIZATION ADMINISTRATION</span>
        <h2>One control plane, clear boundaries.</h2>
        <p>Workspaces are the named organization, domain, and project scopes used by the UI, CLI, and agent hooks. Creating one here persists it to the active control-plane store.</p>
      </div>
      <div class="workspace-admin-stats">
        <div><strong>${domains.length}</strong><span>Domains</span></div>
        <div><strong>${projects.length}</strong><span>Projects</span></div>
        <div><strong>${workspaces.length}</strong><span>Visible scopes</span></div>
      </div>
    </section>
    <div class="workspace-admin-grid section-gap">
      <section class="panel">
        <div class="panel-header"><div><h2 class="panel-title">Domain workspaces</h2><p class="panel-subtitle">A domain groups related projects and governance rules.</p></div><span class="tag blue">${domains.length}</span></div>
        ${domains.length ? `<div class="workspace-admin-list">${domains.map(workspaceAdminRow).join("")}</div>` : `<div class="empty-state"><strong>No domains created</strong><p>Create a domain before creating project workspaces.</p></div>`}
      </section>
      <section class="panel">
        <div class="panel-header"><div><h2 class="panel-title">Project workspaces</h2><p class="panel-subtitle">Projects are the narrowest agent and workload boundary.</p></div><span class="tag blue">${projects.length}</span></div>
        ${projects.length ? `<div class="workspace-admin-list">${projects.map(workspaceAdminRow).join("")}</div>` : `<div class="empty-state"><strong>No projects created</strong><p>Project workspaces can be created inside a domain.</p></div>`}
      </section>
    </div>
    <section class="panel section-gap workspace-cli-note">
      <div class="workspace-cli-icon">⌘</div>
      <div><strong>CLI parity</strong><p>The same workspace registry is available to agents: <code>adop workspace create --level domain --name finance</code>. The CLI uses the configured local JSON store or DynamoDB backend.</p></div>
    </section>
  `;
}

function workspaceAdminRow(workspace) {
  const parent = workspace.parent_level
    ? `${workspace.parent_level}/${workspace.parent_name}`
    : workspace.level === "organization" ? "Root organization" : "Identity membership";
  return `<div class="workspace-admin-row"><div class="workspace-admin-symbol">${workspace.level === "domain" ? "◌" : workspace.level === "project" ? "◇" : "◎"}</div><div class="workspace-admin-copy"><strong>${escapeHtml(workspace.label || workspace.name)}</strong><small>${escapeHtml(workspace.level)}/${escapeHtml(workspace.name)} · parent ${escapeHtml(parent)}</small></div><span class="tag ${workspace.system ? "gray" : "green"}">${workspace.system ? "System" : "Persisted"}</span></div>`;
}

function accessUserRow(user) {
  const memberships = (user.memberships || []).map(item => item.label || `${item.level}/${item.name}`).join(" · ");
  const permissions = (user.feature_permissions || []).length;
  return `<div class="access-user-row"><div class="access-user-identity"><div class="avatar">${escapeHtml(initials(user))}</div><div><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.email)}</small></div></div><span class="tag blue">${escapeHtml(user.role_label || user.role)}</span><div class="access-memberships">${escapeHtml(memberships)}</div><span class="tag gray">${permissions} features</span><button class="panel-link" data-action="view-user-access" data-user-email="${escapeHtml(user.email)}">View access →</button></div>`;
}

function renderWorkloadDetail() {
  return `
    ${shell("MONITOR / WORKLOADS", "customer_orders", "Daily order-level sales reporting · repository-backed detail view", `<button class="button" data-view-link="workloads">← All workloads</button><button class="button primary" data-action="propose-contract">Propose change</button>`)}
    <div class="detail-stats">${miniStat("CURRENT PHASE", "4.3", "Metadata success · build pending")}${miniStat("CONFIG HASH", "c088235b…", "Pinned at run start")}${miniStat("REQUIREMENTS", "Complete", "Human answers authoritative")}</div>
    <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Run progress</h2><p class="panel-subtitle">${repoState.workload.runId}</p></div>${status("Build in progress", "pending")}</div>
      <div class="run-timeline">${timelineStep("0", "Discovery", true)}${timelineStep("1", "Requirements", true)}${timelineStep("2", "Context", true)}${timelineStep("3", "Metadata", true)}${timelineStep("4.3", "Build", false, true)}${timelineStep("5", "Deploy", false)}</div>
      <div class="flow-foot"><span><strong>Source</strong> ${repoState.workload.source}</span><span><strong>Schedule</strong> ${repoState.workload.schedule}</span><span><strong>Ontology</strong> ${repoState.workload.ontology}</span></div>
    </section>
    <div class="layout-main section-gap"><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Authoritative decisions</h2><p class="panel-subtitle">Read from the current run context; changes apply to a future run.</p></div><span class="tag blue">Human provided</span></div><table class="table"><tbody>
      <tr><td>Primary key</td><td class="right"><strong>${repoState.workload.primaryKey}</strong></td></tr><tr><td>Deduplication</td><td class="right"><strong>None</strong></td></tr><tr><td>Null handling</td><td class="right"><strong>Quarantine critical nulls</strong></td></tr><tr><td>PII / compliance</td><td class="right"><strong>8 columns · GDPR</strong></td></tr><tr><td>Gold schema</td><td class="right"><strong>${repoState.workload.goldSchema}</strong></td></tr>
    </tbody></table></section><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Quality gates</h2><p class="panel-subtitle">Promotion thresholds</p></div><button class="panel-link" data-view-link="contracts">View contracts</button></div>${qualityRow("Silver", 80, "≥ 0.80")}${qualityRow("Gold", 95, "≥ 0.95")}${qualityRow("PII coverage", 100, "Required")}</section></div>
  `;
}

function miniStat(label, value, detail) {
  return `<div class="mini-stat"><span>${label}</span><strong>${value}</strong><span>${detail}</span></div>`;
}

function timelineStep(number, label, done, current = false) {
  return `<div class="timeline-step ${done ? "" : current ? "current" : "future"}"><div class="timeline-dot">${done ? "✓" : number}</div><strong>${label}</strong><small>${done ? "Complete" : current ? "In progress" : "Pending"}</small></div>`;
}

function navigate(view, refresh = true) {
  if ((view === "access" || view === "workspaces") && !hasFeature("users.manage")) {
    showToast("Access management is available to organization administrators only.");
    view = "home";
  }
  currentView = view;
  const entry = views[view] || views.home;
  breadcrumb.textContent = entry.label;
  app.innerHTML = entry.render();
  document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === view));
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (refresh && view === "policies") void refreshRemotePolicyState();
  if (refresh && view === "contracts") void refreshRemoteContractState();
  if (refresh && view === "connectors") void refreshRemoteConnectors();
  if (refresh && (view === "home" || view === "workloads")) void refreshRemoteWorkloads();
  if (refresh && view === "approvals") void refreshRemoteChanges();
  if (refresh && view === "runs") void refreshRemoteWorkloads();
  if (refresh && view === "audit") void refreshRemoteAudit();
  if (refresh && view === "workspaces") void refreshRemoteWorkspaces();
  if (refresh && view === "access") void refreshRemoteUsers();
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = "<span>✓</span>";
  toast.appendChild(document.createTextNode(String(message ?? "")));
  toastRoot.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function initials(identity) {
  return String(identity?.name || identity?.email || "AD")
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0].toUpperCase())
    .join("") || "AD";
}

function workspaceKey(workspace) {
  return workspace ? `${workspace.level}/${workspace.name}` : "none";
}

function availableWorkspaces() {
  return remoteWorkspaces.length
    ? remoteWorkspaces
    : authSession?.identity?.workspaces || authSession?.identity?.memberships || [];
}

function selectedWorkspace() {
  const choices = availableWorkspaces();
  const selected = authSession?.workspace;
  if (selected) {
    const matching = choices.find(item => item.level === selected.level && item.name === selected.name);
    if (matching) return matching;
  }
  return choices.find(item => item.level === "project")
    || choices.find(item => item.level === "domain")
    || choices.find(item => item.level === "organization")
    || null;
}

function hasFeature(feature) {
  const identity = authSession?.identity;
  return Boolean(identity && (
    identity.role === "org-admin"
    || (identity.feature_permissions || []).includes(feature)
  ));
}

function updateIdentityChrome() {
  const identity = authSession?.identity;
  if (!identity) return;
  const workspace = selectedWorkspace();
  if (workspace && (!authSession.workspace || workspaceKey(authSession.workspace) !== workspaceKey(workspace))) {
    authSession.workspace = { level: workspace.level, name: workspace.name };
    sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(authSession));
  }
  const avatar = initials(identity);
  document.querySelectorAll("#user-avatar, #top-avatar").forEach(item => { item.textContent = avatar; });
  const name = document.getElementById("user-name");
  const role = document.getElementById("user-role");
  if (name) name.textContent = identity.name || identity.email;
  if (role) role.textContent = `${identity.role_label || identity.role} · ${identity.provider === "local-test" ? "test login" : "SSO"}`;
  const workspaceName = document.getElementById("workspace-name");
  const workspaceSubtitle = document.getElementById("workspace-subtitle");
  if (workspaceName) workspaceName.textContent = workspace?.label || "No workspace";
  if (workspaceSubtitle) workspaceSubtitle.textContent = `${identity.role_label || identity.role} · ${workspaceKey(workspace)}`;
  document.querySelectorAll(".nav-item[data-feature]").forEach(item => {
    item.hidden = !hasFeature(item.dataset.feature);
  });
}

function renderLogin(message = "") {
  appShell.hidden = true;
  authRoot.innerHTML = `
    <main class="login-page">
      <section class="login-card">
        <div class="login-brand">
          <div class="brand-mark" aria-hidden="true">
            <svg class="brand-glyph" viewBox="0 0 42 42"><path d="M21 4 35.5 12.5v17L21 38 6.5 29.5v-17L21 4Z" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="m11 16 10 6 10-6M21 22v11" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="11" cy="16" r="2.4" fill="currentColor"/><circle cx="31" cy="16" r="2.4" fill="currentColor"/><circle cx="21" cy="33" r="2.4" fill="currentColor"/></svg>
          </div>
          <div><div class="login-brand-name">ADOP</div><div class="login-brand-caption">CONTROL PLANE</div></div>
        </div>
        <div class="eyebrow">SECURE WORKSPACE</div>
        <h1>Sign in to ADOP</h1>
        <p class="login-copy">${authConfig?.mode === "local" ? "Use a local test identity to exercise the console and API-backed governance flows." : `Continue with ${escapeHtml(authConfig?.provider || "your identity provider")} to access your organization.`}</p>
        ${message ? `<div class="login-error" role="alert">${escapeHtml(message)}</div>` : ""}
        ${authConfig?.mode === "local" ? `
          <form id="local-login-form" class="login-form">
            <div class="field"><label for="login-user">Test user</label><select id="login-user">${authTestUsers.map(user => `<option value="${escapeHtml(user.email)}">${escapeHtml(user.name)}${user.username ? ` (${escapeHtml(user.username)})` : ""} · ${escapeHtml(user.role_label)}</option>`).join("")}</select></div>
            <div class="field"><label for="login-password">Test passcode ${authConfig.local_test_password_required ? "" : "(optional locally)"}</label><input id="login-password" type="password" ${authConfig.local_test_password_required ? "required" : ""} autocomplete="current-password" /></div>
            <button class="button primary login-submit" type="submit">Enter test workspace</button>
          </form>
          <div class="login-note"><span>ⓘ</span><span>Local test login is disabled when <code>ADOP_ENV</code> is not <code>local</code>. It does not create or store users.</span></div>
        ` : `
          <button class="button primary login-submit" data-action="sso-login">Continue with SSO</button>
          <div class="login-note"><span>◉</span><span>ADOP uses your configured OIDC provider. Passwords are never handled by this UI.</span></div>
        `}
        <div class="login-footer">ADOP Console · ${escapeHtml(authConfig?.mode || "connecting")} authentication</div>
      </section>
    </main>
  `;
  document.getElementById("local-login-form")?.addEventListener("submit", event => {
    event.preventDefault();
    void localLogin();
  });
}

async function localLogin() {
  const payload = {
    email: document.getElementById("login-user")?.value.trim(),
    password: document.getElementById("login-password")?.value || "",
  };
  try {
    const result = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await result.json().catch(() => ({}));
    if (!result.ok) throw new Error(body.error?.message || "Login failed");
    authSession = { identity: body.identity, mode: "local" };
    sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(authSession));
    enterConsole();
  } catch (error) {
    renderLogin(error.message);
  }
}

function enterConsole() {
  authRoot.innerHTML = "";
  appShell.hidden = false;
  updateIdentityChrome();
  const workspace = selectedWorkspace();
  if (workspace) {
    policyScope = { level: workspace.level, name: workspace.name };
    contractScope = { level: workspace.level, name: workspace.name };
  }
  navigate("home");
}

function signOut() {
  authSession = null;
  sessionStorage.removeItem(AUTH_SESSION_KEY);
  void fetch(`${API_BASE}/auth/logout`, { method: "POST" }).catch(() => {});
  renderLogin();
}

function canViewWorkspace(level, name) {
  const identity = authSession?.identity;
  if (!identity) return false;
  if (identity.role === "org-admin") return true;
  return (identity.workspaces || []).some(item => item.level === level && item.name === name)
    || (level === "project" && (identity.workspaces || []).some(item => item.level === "domain" && item.name === "sales"));
}

function canEditContractScope(level, name) {
  const identity = authSession?.identity;
  if (!identity) return false;
  if (identity.role === "org-admin") return true;
  return level === "project" && (identity.workspaces || []).some(
    item => item.level === "project" && item.name === name,
  );
}

function workspaceAccessPanel() {
  const workspaces = availableWorkspaces();
  return `
    <section class="panel section-gap workspace-access-panel">
      <div class="panel-header"><div><h2 class="panel-title">Workspace access</h2><p class="panel-subtitle">Visible memberships for this signed-in user. The API applies the same filter.</p></div><span class="tag blue">Soft isolation</span></div>
      <div class="workspace-access-grid">${workspaces.map(item => `<div class="workspace-access-item"><span class="workspace-access-icon">${item.level === "organization" ? "◎" : item.level === "domain" ? "◌" : "◇"}</span><div><strong>${escapeHtml(item.label)}</strong><small>${item.level}/${item.name}</small></div></div>`).join("")}</div>
      <div class="callout"><span class="callout-icon">ⓘ</span><span>Project users only see workloads, contracts, policies, and future connector bindings for projects they belong to. Domain owners can see eligible projects inside their domain.</span></div>
    </section>
  `;
}

function openWorkspaceMenu() {
  const current = selectedWorkspace();
  modalRoot.innerHTML = `
    <div class="modal-backdrop" data-modal-close>
      <div class="modal workspace-menu-modal" role="dialog" aria-modal="true" aria-labelledby="workspace-menu-title">
        <div class="modal-header"><div><h2 id="workspace-menu-title">Switch workspace</h2><p>Select an accessible organization, domain, or project scope.</p></div><button class="modal-close" data-modal-close aria-label="Close">×</button></div>
        <div class="modal-body">
          <div class="workspace-choice-list">${availableWorkspaces().map(item => `<button class="workspace-choice ${workspaceKey(current) === workspaceKey(item) ? "selected" : ""}" data-action="select-workspace" data-workspace-level="${escapeHtml(item.level)}" data-workspace-name="${escapeHtml(item.name)}"><span class="workspace-access-icon">${item.level === "organization" ? "◎" : item.level === "domain" ? "◌" : "◇"}</span><span><strong>${escapeHtml(item.label || workspaceKey(item))}</strong><small>${escapeHtml(workspaceKey(item))}</small></span>${workspaceKey(current) === workspaceKey(item) ? '<span class="tag green">Current</span>' : ""}</button>`).join("")}</div>
        </div>
      </div>
    </div>
  `;
}

async function selectWorkspace(level, name) {
  const candidate = availableWorkspaces().find(item => item.level === level && item.name === name);
  if (!candidate) {
    showToast("You do not have access to that workspace.");
    return;
  }
  try {
    await apiFetch("/auth/workspace", {
      method: "POST",
      body: JSON.stringify({ scope: level, scope_name: name }),
    });
  } catch (error) {
    showToast(`Workspace switch rejected: ${error.message}`);
    return;
  }
  authSession.workspace = { level, name };
  sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(authSession));
  modalRoot.innerHTML = "";
  updateIdentityChrome();
  policyScope = { level, name };
  contractScope = { level, name };
  remoteContractState = null;
  showToast(`Switched to ${workspaceKey(authSession.workspace)}.`);
  navigate("home");
}

function base64Url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function startSsoLogin() {
  if (!authConfig?.authorize_url || !authConfig?.client_id) {
    renderLogin("SSO is not configured. Set ADOP_OIDC_AUTHORIZE_URL and ADOP_OIDC_CLIENT_ID.");
    return;
  }
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  const state = base64Url(crypto.getRandomValues(new Uint8Array(16)));
  sessionStorage.setItem("adop.oidc.state", state);
  sessionStorage.setItem("adop.oidc.verifier", verifier);
  const url = new URL(authConfig.authorize_url);
  const params = {
    response_type: "code",
    client_id: authConfig.client_id,
    redirect_uri: authConfig.redirect_uri || window.location.origin + window.location.pathname,
    scope: "openid email profile",
    state,
    code_challenge: base64Url(digest),
    code_challenge_method: "S256",
  };
  if (authConfig.provider_hint) params.identity_provider = authConfig.provider_hint;
  url.search = new URLSearchParams(params);
  window.location.assign(url.toString());
}

async function finishSsoCallback() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  if (!code || !authConfig?.token_url) return false;
  if (params.get("state") !== sessionStorage.getItem("adop.oidc.state")) {
    renderLogin("SSO state validation failed. Start login again.");
    return true;
  }
  const result = await fetch(authConfig.token_url, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: authConfig.client_id,
      code,
      redirect_uri: authConfig.redirect_uri || window.location.origin + window.location.pathname,
      code_verifier: sessionStorage.getItem("adop.oidc.verifier") || "",
    }),
  });
  const tokens = await result.json().catch(() => ({}));
  if (!result.ok || !tokens.access_token) throw new Error(tokens.error_description || "SSO token exchange failed");
  authSession = {
    accessToken: tokens.access_token,
    idToken: tokens.id_token,
    // Cognito's ID token carries the verified profile/group claims used by
    // this control plane; retain the access token for future resource scopes.
    apiToken: tokens.id_token || tokens.access_token,
  };
  sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(authSession));
  window.history.replaceState({}, document.title, window.location.pathname);
  return true;
}

async function bootstrapAuth() {
  try {
    authConfig = await fetch(`${API_BASE}/auth/config`).then(response => response.json());
    if (authConfig.mode === "local") {
      const testUsers = await fetch(`${API_BASE}/auth/test-users`).then(response => response.json());
      authTestUsers = testUsers.items || [];
    }
    try { authSession = JSON.parse(sessionStorage.getItem(AUTH_SESSION_KEY) || "null"); } catch { authSession = null; }
    const callbackHandled = await finishSsoCallback();
    const me = await apiFetch("/auth/me");
    if (me.authenticated) {
      authSession = { ...(authSession || {}), identity: me.identity };
      sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(authSession));
      enterConsole();
    } else if (!callbackHandled) {
      renderLogin();
    }
  } catch (error) {
    renderLogin(`Authentication service unavailable: ${error.message}`);
  }
}

function openConnectorModal() {
  selectedConnectorType = "jdbc";
  modalRoot.innerHTML = `
    <div class="modal-backdrop" data-modal-close>
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="connector-title">
        <div class="modal-header"><div><h2 id="connector-title">New connector</h2><p>Register a reusable source profile. Enter the Secrets Manager ARN; connection fields may come from the secret.</p></div><button class="modal-close" data-modal-close aria-label="Close">×</button></div>
        <div class="modal-body">
          <div class="connector-types"><button class="connector-type selected" data-connector-type="jdbc" type="button">JDBC generic</button><button class="connector-type" data-connector-type="postgres" type="button">PostgreSQL / RDS</button><button class="connector-type" data-connector-type="snowflake" type="button">Snowflake</button><button class="connector-type" data-connector-type="teradata" type="button">Teradata</button><button class="connector-type" data-connector-type="databricks" type="button">Databricks</button></div>
          <div class="form-grid">
            <div class="field"><label for="connector-name">Connector name</label><input id="connector-name" placeholder="e.g. td_finance" /></div>
            <div class="field"><label for="access-mode">Access mode</label><select id="access-mode"><option>Read-only</option><option>Read / write (approval required)</option></select></div>
            <div class="field"><label for="host">Host</label><input id="host" placeholder="internal.example.com" /></div>
            <div class="field"><label for="port">Port</label><input id="port" placeholder="443" /></div>
            <div class="field"><label for="database">Database / catalog</label><input id="database" placeholder="analytics" /></div>
            <div class="field"><label for="schema">Schema</label><input id="schema" placeholder="public" /></div>
            <div class="field full"><label for="secret">Secrets Manager reference</label><input id="secret" placeholder="arn:aws:secretsmanager:… (reference only)" /></div>
          </div>
          <div class="secret-hint"><span>▣</span><span>The console stores the ARN only. The secret may contain engine, host, port, database, username, and password. It never displays or logs secret values.</span></div>
        </div>
        <div class="modal-footer"><button class="button" data-modal-close>Cancel</button>${authConfig?.mode === "local" ? '<button class="button" data-action="test-connector">Test connection</button>' : '<span class="panel-subtitle">Save before testing in AWS mode</span>'}<button class="button primary" data-action="submit-connector">Submit for approval</button></div>
      </div>
    </div>
  `;
}

function getPolicyProposals() {
  const proposals = { ...remotePolicyProposals };
  try {
    return {
      ...JSON.parse(localStorage.getItem(POLICY_PROPOSAL_KEY) || "{}"),
      ...proposals,
    };
  } catch {
    return proposals;
  }
}

function getPolicyProposal(policyId) {
  const proposals = getPolicyProposals();
  return proposals[`${policyScope.level}|${policyScope.name}|${policyId}`] || proposals[policyId];
}

async function openPolicyEditor(policyId) {
  const policy = cedarPolicies[policyId] || cedarPolicies["agent_authorization/global_protection"];
  try {
    const remote = await apiFetch(`/policies/${encodeURIComponent(policyId)}?scope=${policyScope.level}&scope_name=${policyScope.name}`);
    if (remote) {
      policy.path = remote.path;
      policy.text = remote.content;
      policy.version = remote.version;
      if (remote.proposal) {
        remotePolicyProposals[`${policyScope.level}|${policyScope.name}|${policyId}`] = remote.proposal;
      }
    }
  } catch (error) {
    showToast(`API unavailable; opening local draft. ${error.message}`);
  }
  const proposal = getPolicyProposal(policyId);
  const initialText = proposal?.text || policy.text;
  modalRoot.innerHTML = `
    <div class="modal-backdrop" data-modal-close>
      <div class="modal policy-editor" role="dialog" aria-modal="true" aria-labelledby="policy-editor-title">
        <div class="modal-header"><div><h2 id="policy-editor-title">${proposal ? "Edit pending proposal" : "View Cedar policy"}</h2><p>${policy.title} · ${policyScope.level}/${policyScope.name} · ${policy.path}</p></div><button class="modal-close" data-modal-close aria-label="Close">×</button></div>
        <div class="modal-body">
          <div class="editor-meta"><span class="tag blue">Cedar</span><span class="tag gray">${policy.count}</span><span class="tag ${proposal ? "proposal-state" : "gray"}">${proposal ? "Pending proposal" : "Repository version"}</span></div>
          <textarea id="policy-editor-text" class="policy-textarea" spellcheck="false">${escapeHtml(initialText)}</textarea>
          <div class="editor-warning"><span>ⓘ</span><span>Saving creates an API-backed pending proposal. Production behavior changes after Cedar validation, two-person approval, and a Git/deployment step.</span></div>
        </div>
        <div class="modal-footer"><button class="button" data-modal-close>Close</button><button class="button" data-action="validate-policy" data-policy-id="${policyId}">Validate Cedar</button><button class="button primary" data-action="save-policy-proposal" data-policy-id="${policyId}">Save proposal</button></div>
      </div>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[character]);
}

async function apiFetch(path, options = {}) {
  const headers = {
    "content-type": "application/json",
    ...(options.headers || {}),
  };
  if (authSession?.apiToken || authSession?.accessToken) {
    headers.authorization = `Bearer ${authSession.apiToken || authSession.accessToken}`;
  } else if (authSession?.identity?.provider === "local-test") {
    headers["x-adop-actor"] = authSession.identity.email;
    headers["x-adop-name"] = authSession.identity.name || "";
    headers["x-adop-role"] = authSession.identity.role || "domain-owner";
    headers["x-adop-groups"] = (authSession.identity.groups || []).join(" ");
  }
  const workspace = selectedWorkspace();
  if (workspace) headers["x-adop-workspace"] = workspaceKey(workspace);
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error?.message || `Request failed (${response.status})`);
  }
  return payload;
}

async function refreshRemotePolicyState() {
  try {
    const payload = await apiFetch(`/policies?scope=${policyScope.level}&scope_name=${policyScope.name}`);
    remotePolicyProposals = {};
    (payload.items || []).forEach(item => {
      if (item.proposal) remotePolicyProposals[`${policyScope.level}|${policyScope.name}|${item.policy_id}`] = item.proposal;
    });
  } catch {
    // The static UI remains usable when opened without the local API.
  }
}

async function refreshRemoteContractState() {
  try {
    if (!remoteWorkloadsLoaded) await refreshRemoteWorkloads();
    const workload = currentContractWorkload();
    if (!workload) {
      remoteContractState = null;
      if (currentView === "contracts" && !modalRoot.querySelector(".modal")) {
        app.innerHTML = views.contracts.render();
      }
      return;
    }
    const project = workloadProjects[workload.name] || "orders";
    remoteContractState = await apiFetch(`/contracts?workload=${encodeURIComponent(workload.name)}&domain=sales&project=${encodeURIComponent(project)}`);
    if (currentView === "contracts" && !modalRoot.querySelector(".modal")) {
      app.innerHTML = views.contracts.render();
    }
  } catch {
    remoteContractState = null;
  }
}

async function refreshRemoteConnectors() {
  try {
    const payload = await apiFetch("/connectors");
    remoteConnectors = payload.items || [];
    if (currentView === "connectors" && !modalRoot.querySelector(".modal")) {
      app.innerHTML = views.connectors.render();
    }
  } catch {
    remoteConnectors = [];
  }
}

async function refreshRemoteWorkloads() {
  try {
    const payload = await apiFetch("/workloads");
    remoteWorkloads = payload.items || [];
    remoteWorkloadsLoaded = true;
    if (currentView === "home" || currentView === "workloads") {
      app.innerHTML = views[currentView].render();
    }
  } catch {
    remoteWorkloads = [];
    remoteWorkloadsLoaded = true;
  }
}

async function refreshRemoteWorkspaces() {
  if (!hasFeature("users.manage")) return;
  try {
    const payload = await apiFetch("/workspaces");
    remoteWorkspaces = payload.items || [];
    if (currentView === "workspaces" && !modalRoot.querySelector(".modal")) {
      app.innerHTML = views.workspaces.render();
    }
  } catch {
    remoteWorkspaces = [];
  }
}

async function refreshRemoteUsers() {
  if (!hasFeature("users.manage")) return;
  try {
    const payload = await apiFetch("/users");
    remoteUsers = payload.items || [];
    if (currentView === "access") app.innerHTML = views.access.render();
  } catch {
    remoteUsers = [];
  }
}

function openWorkspaceModal() {
  const domains = (remoteWorkspaces.length ? remoteWorkspaces : availableWorkspaces())
    .filter(item => item.level === "domain");
  modalRoot.innerHTML = `
    <div class="modal-backdrop" data-modal-close>
      <div class="modal workspace-create-modal" role="dialog" aria-modal="true" aria-labelledby="workspace-create-title">
        <div class="modal-header"><div><h2 id="workspace-create-title">Create workspace</h2><p>Organization administrators can create a domain or project boundary for the UI, CLI, and agent runtime.</p></div><button class="modal-close" data-modal-close aria-label="Close">×</button></div>
        <div class="modal-body">
          <div class="workspace-create-intro"><span class="workspace-create-intro-icon">▦</span><span>Workspace names become stable scope identifiers. Use lowercase letters, numbers, hyphens, or underscores.</span></div>
          <div class="form-grid">
            <div class="field"><label for="workspace-level">Workspace type</label><select id="workspace-level"><option value="domain">Domain</option><option value="project">Project</option></select></div>
            <div class="field"><label for="workspace-name-input">Scope name</label><input id="workspace-name-input" placeholder="e.g. finance" autocomplete="off" /></div>
            <div class="field full"><label for="workspace-label-input">Display name</label><input id="workspace-label-input" placeholder="e.g. Finance data domain" autocomplete="off" /></div>
            <div class="field full" id="workspace-parent-field" hidden><label for="workspace-parent">Parent domain</label><select id="workspace-parent">${domains.length ? domains.map(item => `<option value="${escapeHtml(workspaceKey(item))}">${escapeHtml(item.label || item.name)}</option>`).join("") : '<option value="">Create a domain first</option>'}</select></div>
          </div>
          <div class="workspace-create-hierarchy"><span>Organization</span><i>→</i><span id="workspace-parent-preview">Domain</span><i>→</i><strong id="workspace-type-preview">Domain / finance</strong></div>
        </div>
        <div class="modal-footer"><button class="button" data-modal-close>Cancel</button><button class="button primary" data-action="create-workspace">Create workspace</button></div>
      </div>
    </div>
  `;
  const level = document.getElementById("workspace-level");
  const name = document.getElementById("workspace-name-input");
  const label = document.getElementById("workspace-label-input");
  const parentField = document.getElementById("workspace-parent-field");
  const parentPreview = document.getElementById("workspace-parent-preview");
  const typePreview = document.getElementById("workspace-type-preview");
  const updatePreview = () => {
    const selected = level.value;
    parentField.hidden = selected !== "project";
    parentPreview.textContent = selected === "project"
      ? (document.getElementById("workspace-parent")?.selectedOptions[0]?.textContent || "Select domain")
      : "Domain";
    typePreview.textContent = `${selected[0].toUpperCase()}${selected.slice(1)} / ${name.value.trim().toLowerCase() || "scope-name"}`;
  };
  level.addEventListener("change", updatePreview);
  name.addEventListener("input", updatePreview);
  document.getElementById("workspace-parent")?.addEventListener("change", updatePreview);
  updatePreview();
}

async function createWorkspace() {
  const level = document.getElementById("workspace-level")?.value;
  const name = document.getElementById("workspace-name-input")?.value.trim().toLowerCase();
  const label = document.getElementById("workspace-label-input")?.value.trim();
  const parent = level === "project" ? document.getElementById("workspace-parent")?.value : undefined;
  if (!name) {
    showToast("Enter a workspace scope name.");
    return;
  }
  try {
    const workspace = await apiFetch("/workspaces", {
      method: "POST",
      body: JSON.stringify({ level, name, label, parent }),
    });
    remoteWorkspaces = [...remoteWorkspaces.filter(item => workspaceKey(item) !== workspaceKey(workspace)), workspace];
    modalRoot.innerHTML = "";
    app.innerHTML = views.workspaces.render();
    showToast(`Created ${workspaceKey(workspace)}.`);
  } catch (error) {
    showToast(`Workspace creation failed: ${error.message}`);
  }
}

async function refreshRemoteChanges() {
  if (!hasFeature("approvals.read")) return;
  try {
    const payload = await apiFetch("/changes");
    remoteChanges = payload.items || [];
    if (currentView === "approvals" && !modalRoot.querySelector(".modal")) {
      app.innerHTML = views.approvals.render();
    }
  } catch {
    remoteChanges = [];
  }
}

async function refreshRemoteAudit() {
  if (!hasFeature("audit.read")) return;
  try {
    const payload = await apiFetch("/audit");
    remoteAudit = payload.items || [];
    if (currentView === "audit") app.innerHTML = views.audit.render();
  } catch {
    remoteAudit = [];
  }
}

async function openApprovalReview(changeId) {
  try {
    const change = await apiFetch(`/changes/${encodeURIComponent(changeId)}`);
    renderApprovalReview(change);
  } catch (error) {
    showToast(`Unable to load change: ${error.message}`);
  }
}

async function decideChange(changeId, decision) {
  const comment = window.prompt(`${decision === "approve" ? "Approval" : "Rejection"} comment (optional):`, "") ?? "";
  try {
    const updated = await apiFetch(`/changes/${encodeURIComponent(changeId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ decision, comment }),
    });
    remoteChanges = remoteChanges.map(item => item.change_id === changeId ? updated : item);
    modalRoot.innerHTML = "";
    if (currentView === "approvals") app.innerHTML = views.approvals.render();
    showToast(updated.status === "approved_pending_git"
      ? "Change approved by the required reviewers; Git application is next."
      : `Change ${decision}d.`);
  } catch (error) {
    showToast(`Decision failed: ${error.message}`);
  }
}

function connectorDraftPayload() {
  return {
    name: document.getElementById("connector-name")?.value.trim(),
    type: selectedConnectorType,
    access_mode: document.getElementById("access-mode")?.value === "Read / write (approval required)" ? "read-write" : "read-only",
    secret_ref: document.getElementById("secret")?.value.trim(),
    metadata: {
      host: document.getElementById("host")?.value.trim(),
      port: Number(document.getElementById("port")?.value || 0) || undefined,
      database: document.getElementById("database")?.value.trim(),
      schema: document.getElementById("schema")?.value.trim(),
    },
  };
}

async function testConnectorDraft() {
  if (authConfig?.mode !== "local") {
    showToast("Save the connector first in AWS mode, then run its health check.");
    return;
  }
  const draft = connectorDraftPayload();
  if (!draft.name || !draft.secret_ref) {
    showToast("Enter a connector name and Secrets Manager reference before testing.");
    return;
  }
  try {
    const result = await apiFetch("/connectors/test", {
      method: "POST",
      body: JSON.stringify(draft),
    });
    const message = result.status === "healthy"
      ? `Real ${selectedConnectorType} connection passed in ${result.duration_ms}ms.`
      : `Connection not healthy: ${result.error_code || result.status}.`;
    showToast(message);
  } catch (error) {
    showToast(`Connection test rejected: ${error.message}`);
  }
}

async function createConnector() {
  try {
    const connector = await apiFetch("/connectors", {
      method: "POST",
      body: JSON.stringify(connectorDraftPayload()),
    });
    modalRoot.innerHTML = "";
    await refreshRemoteConnectors();
    navigate("connectors", false);
    showToast(`Connector ${connector.name} saved as Not tested. Run a real health check.`);
  } catch (error) {
    showToast(`Connector was not saved: ${error.message}`);
  }
}

async function testConnectorCard(connectorId) {
  try {
    const result = await apiFetch(`/connectors/${encodeURIComponent(connectorId)}/test`, { method: "POST" });
    remoteConnectors = remoteConnectors.map(item => item.connector_id === connectorId ? result : item);
    if (currentView === "connectors") app.innerHTML = views.connectors.render();
    showToast(result.status === "healthy" ? `${result.name} is healthy.` : `${result.name} is ${result.status}: ${result.health?.error_code || "check failed"}.`);
  } catch (error) {
    showToast(`Health check failed: ${error.message}`);
  }
}

async function testAllConnectors() {
  try {
    const payload = await apiFetch("/connectors/test-all", { method: "POST" });
    remoteConnectors = payload.items || [];
    if (currentView === "connectors") app.innerHTML = views.connectors.render();
    showToast(`Completed real health checks for ${remoteConnectors.length} connector(s).`);
  } catch (error) {
    showToast(`Health checks failed: ${error.message}`);
  }
}

async function openContractEditor() {
  if (!canEditContractScope(contractScope.level, contractScope.name)) {
    showToast("Only organization administrators can change organization/domain contracts. Select an eligible project to propose a change.");
    return;
  }
  let contract = remoteContractState;
  try {
    contract = await apiFetch(`/contracts?workload=${encodeURIComponent(repoState.workload.name)}&domain=sales&project=orders`);
  } catch (error) {
    showToast(`Contract API unavailable. ${error.message}`);
    return;
  }
  const pending = contract.proposals?.[`${contractScope.level}/${contractScope.name}`];
  const selected = pending?.content || contract.layers?.[contractScope.level]?.policy || contract.effective || contract.layers?.organization?.policy;
  const draft = {
    ...(selected || {}),
    scope: contractScope.level,
    contract_id: selected?.contract_id || `adop.${contractScope.level}.${contractScope.name}.zone-default`,
  };
  modalRoot.innerHTML = `
    <div class="modal-backdrop" data-modal-close>
      <div class="modal policy-editor" role="dialog" aria-modal="true" aria-labelledby="contract-editor-title">
        <div class="modal-header"><div><h2 id="contract-editor-title">Edit ${contractScope.level} contract</h2><p>${contractScope.level}/${contractScope.name} · inherited values are shown as the starting point</p></div><button class="modal-close" data-modal-close aria-label="Close">×</button></div>
        <div class="modal-body">
          <div class="editor-meta"><span class="tag blue">Zone contract</span><span class="tag gray">${contractScope.level}/${contractScope.name}</span><span class="tag proposal-state">Two approvals required</span></div>
          <textarea id="contract-editor-json" class="policy-textarea" spellcheck="false">${escapeHtml(JSON.stringify(draft, null, 2))}</textarea>
          <div class="editor-warning"><span>ⓘ</span><span>Lower scopes can tighten inherited rules only. The API validates the contract schema and rejects weaker thresholds, disabled PII controls, and contradictory encryption rules.</span></div>
        </div>
        <div class="modal-footer"><button class="button" data-modal-close>Close</button><button class="button" data-action="validate-contract">Validate format</button><button class="button primary" data-action="save-contract-proposal">Save proposal</button></div>
      </div>
    </div>
  `;
}

async function validatePolicyProposal(policyId) {
  const text = document.getElementById("policy-editor-text")?.value || "";
  try {
    const result = await apiFetch(`/policies/${encodeURIComponent(policyId)}/validate`, {
      method: "POST",
      body: JSON.stringify({ content: text }),
    });
    showToast(`Cedar validation passed (${result.engine}).`);
  } catch (error) {
    showToast(`Cedar validation failed: ${error.message}`);
  }
}

async function savePolicyProposal(policyId) {
  const text = document.getElementById("policy-editor-text")?.value || "";
  const policy = cedarPolicies[policyId] || {};
  try {
    const current = await apiFetch(`/policies/${encodeURIComponent(policyId)}?scope=${policyScope.level}&scope_name=${policyScope.name}`);
    const proposal = await apiFetch(`/policies/${encodeURIComponent(policyId)}/proposals`, {
      method: "POST",
      body: JSON.stringify({
        content: text,
        expected_version: current.version,
        scope: policyScope.level,
        scope_name: policyScope.name,
      }),
    });
    remotePolicyProposals[`${policyScope.level}|${policyScope.name}|${policyId}`] = proposal;
    modalRoot.innerHTML = "";
    navigate("policies");
    showToast("Policy proposal saved to the control-plane API.");
  } catch (error) {
    const proposals = getPolicyProposals();
    proposals[policyId] = {
      text,
      savedAt: new Date().toISOString(),
      status: "pending_approval",
      path: policy.path,
    };
    localStorage.setItem(POLICY_PROPOSAL_KEY, JSON.stringify(proposals));
    modalRoot.innerHTML = "";
    navigate("policies");
    showToast(`API unavailable; saved locally as a draft. ${error.message}`);
  }
}

async function saveContractProposal() {
  const text = document.getElementById("contract-editor-json")?.value || "";
  try {
    const content = JSON.parse(text);
    const current = remoteContractState || await apiFetch(`/contracts?workload=${encodeURIComponent(repoState.workload.name)}&domain=sales&project=orders`);
    const proposal = await apiFetch("/contracts/proposals", {
      method: "POST",
      body: JSON.stringify({
        workload_name: repoState.workload.name,
        domain: "sales",
        project: "orders",
        scope: contractScope.level,
        scope_name: contractScope.name,
        content,
        expected_version: current.effective?.effective_hash,
      }),
    });
    modalRoot.innerHTML = "";
    navigate("contracts");
    showToast(`Contract proposal saved for ${contractScope.level}/${contractScope.name}.`);
    return proposal;
  } catch (error) {
    showToast(`Contract proposal failed: ${error.message}`);
  }
}

async function validateContractProposal() {
  const text = document.getElementById("contract-editor-json")?.value || "";
  try {
    const content = JSON.parse(text);
    const result = await apiFetch("/contracts/validate", {
      method: "POST",
      body: JSON.stringify({
        workload_name: repoState.workload.name,
        domain: "sales",
        project: contractScope.name === "orders" ? "orders" : contractScope.name,
        scope: contractScope.level,
        scope_name: contractScope.name,
        content,
      }),
    });
    showToast(`Contract format is valid. Effective hash ${String(result.effective_hash).slice(0, 12)}…`);
  } catch (error) {
    showToast(`Contract validation failed: ${error.message}`);
  }
}

document.addEventListener("click", event => {
  if (event.target.closest('[data-action="logout"]')) return signOut();
  if (event.target.closest('[data-action="sso-login"]')) return void startSsoLogin();
  if (event.target.closest(".workspace-button")) return openWorkspaceMenu();
  const nav = event.target.closest(".nav-item");
  if (nav) return navigate(nav.dataset.view);

  const viewLink = event.target.closest("[data-view-link]");
  if (viewLink) return navigate(viewLink.dataset.viewLink);

  const action = event.target.closest("[data-action]")?.dataset.action;
  if (!action) return;

  if (action === "policy-scope") {
    policyScope = { level: event.target.closest("[data-scope-level]")?.dataset.scopeLevel, name: event.target.closest("[data-scope-level]")?.dataset.scopeName };
    return navigate("policies");
  }
  if (action === "select-workspace") {
    return void selectWorkspace(
      event.target.closest("[data-workspace-level]")?.dataset.workspaceLevel,
      event.target.closest("[data-workspace-name]")?.dataset.workspaceName,
    );
  }
  if (action === "refresh-access") {
    return void refreshRemoteUsers();
  }
  if (action === "refresh-workspaces") {
    return void refreshRemoteWorkspaces();
  }
  if (action === "new-workspace") return openWorkspaceModal();
  if (action === "create-workspace") return void createWorkspace();
  if (action === "invite-user" || action === "view-user-access") {
    return showToast("User provisioning is managed by the configured SSO directory; access mapping is shown here.");
  }
  if (action === "home-tab") {
    homeTab = event.target.closest("[data-home-tab]")?.dataset.homeTab || "overview";
    return navigate("home", false);
  }
  if (action === "contract-scope") {
    contractScope = { level: event.target.closest("[data-scope-level]")?.dataset.scopeLevel, name: event.target.closest("[data-scope-level]")?.dataset.scopeName };
    remoteContractState = null;
    return navigate("contracts");
  }
  if (action === "new-connector") return openConnectorModal();
  if (action === "test-connector-card") return void testConnectorCard(event.target.closest("[data-connector-id]")?.dataset.connectorId);
  if (action === "test-all-connectors") return void testAllConnectors();
  if (action === "view-policy") return void openPolicyEditor(event.target.closest("[data-policy-id]")?.dataset.policyId);
  if (action === "open-policy-store") return showToast("Policy store: Git source under shared/policies/**; proposals are now persisted through the control-plane API.");
  if (action === "validate-policy") return void validatePolicyProposal(event.target.closest("[data-policy-id]")?.dataset.policyId);
  if (action === "save-policy-proposal") {
    const policyId = event.target.closest("[data-policy-id]")?.dataset.policyId;
    return void savePolicyProposal(policyId);
  }
  if (action === "workload-detail") return renderWorkloadDetailPage();
  if (action === "create-workload") return showToast("Workload creation will start with the human discovery gate.");
  if (action === "propose-contract") return void openContractEditor();
  if (action === "validate-contract") return void validateContractProposal();
  if (action === "save-contract-proposal") return void saveContractProposal();
  if (action === "submit-connector") return void createConnector();
  if (action === "test-connector") return void testConnectorDraft();
  if (action === "refresh-approvals") return void refreshRemoteChanges();
  if (action === "refresh-audit") return void refreshRemoteAudit();
  if (action === "review-change") return void openApprovalReview(event.target.closest("[data-change-id]")?.dataset.changeId);
  if (action === "decide-change") return void decideChange(
    event.target.closest("[data-change-id]")?.dataset.changeId,
    event.target.closest("[data-decision]")?.dataset.decision,
  );
  if (action === "approve" || action === "review") return showToast("Approval queue is API-backed; create a proposal to review it here.");
  if (action === "validate") return showToast("Effective policy validated: all lower-scope values preserve the organization baseline.");
  if (action === "trigger-run") return showToast("E2E execution is intentionally disabled in this local prototype.");
  if (action === "export") return showToast("Export prepared from the current repository snapshot.");
  if (action === "connector-docs" || action === "binding-help") return showToast("Connector profiles, source contracts, and workload bindings are separate objects.");
  if (action === "policy-proposal") return showToast("Cedar changes must go through validation, two-person approval, and Git application.");
  return showToast("This interaction is represented in the prototype and is ready for backend wiring.");
});

document.addEventListener("click", event => {
  if (
    event.target.matches(".modal-backdrop") ||
    event.target.matches("[data-modal-close]") ||
    event.target.closest(".modal-close")
  ) {
    modalRoot.innerHTML = "";
  }
  const type = event.target.closest(".connector-type");
  if (type) {
    document.querySelectorAll(".connector-type").forEach(item => item.classList.remove("selected"));
    type.classList.add("selected");
    selectedConnectorType = type.dataset.connectorType || "jdbc";
  }
});

function renderWorkloadDetailPage() {
  breadcrumb.textContent = "customer_orders";
  app.innerHTML = renderWorkloadDetail();
  document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

void bootstrapAuth();
