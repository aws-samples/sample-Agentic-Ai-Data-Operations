const { test, expect } = require("@playwright/test");

const baseURL = "http://127.0.0.1:4173";

async function settle(page) {
  await page.waitForTimeout(250);
}

test("ADOP Console navigation and scoped governance flows work", async ({ page }) => {
  const browserErrors = [];
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", request => {
    browserErrors.push(`requestfailed: ${request.url()} — ${request.failure()?.errorText}`);
  });

  await page.goto(baseURL, { waitUntil: "networkidle" });
  await expect(page).toHaveTitle("ADOP Console");
  await expect(page.getByRole("heading", { name: "Sign in to ADOP" })).toBeVisible();
  await page.getByRole("button", { name: "Enter test workspace" }).click();
  await expect(page.locator(".user-card")).toContainText("Maya Chen");
  await expect(page.locator(".brand-name")).toHaveText("ADOP");
  await expect(page.locator(".nav-label")).toContainText(["MONITOR", "RULES ENGINE", "INTEGRATIONS", "GOVERNANCE", "ADMINISTER"]);

  for (const view of ["workloads", "runs", "contracts", "connectors", "policies", "approvals", "audit", "home"]) {
    await page.locator(`button.nav-item[data-view="${view}"]`).click();
    await settle(page);
    await expect(page.locator("main h1")).toBeVisible();
  }

  await page.locator('button.nav-item[data-view="workloads"]').click();
  await page.locator(".workload-card").first().click();
  await expect(page.locator("main h1")).toHaveText("customer_orders");
  await page.locator('[data-view-link="workloads"]').click();
  await expect(page.locator("main h1")).toHaveText("Workloads");

  await page.locator('button.nav-item[data-view="connectors"]').click();
  await page.locator('[data-action="new-connector"]').first().click();
  await expect(page.locator("#connector-title")).toHaveText("New connector");
  await page.getByRole("button", { name: "Teradata" }).click();
  await expect(page.locator(".connector-type.selected")).toHaveText("Teradata");
  await page.locator('[data-action="test-connector"]').click();
  await expect(page.locator(".toast", { hasText: "Enter a connector name" })).toBeVisible();
  await page.locator('[data-modal-close].modal-close').click();
  await page.locator('[data-action="test-all-connectors"]').click();
  await expect(page.locator(".toast", { hasText: "Completed real health checks for 0 connector" })).toBeVisible();

  await page.locator('button.nav-item[data-view="approvals"]').click();
  await expect(page.locator("main h1")).toHaveText("Approvals");
  await expect(page.locator('[data-action="approve"]')).toHaveCount(0);
  await page.locator('button.nav-item[data-view="runs"]').click();
  await page.locator('[data-action="trigger-run"]').click();
  await expect(page.locator(".toast", { hasText: "E2E execution is intentionally disabled" })).toBeVisible();
  await page.locator('button.nav-item[data-view="audit"]').click();
  await page.locator('[data-action="export"]').click();
  await expect(page.locator(".toast", { hasText: "Export prepared" })).toBeVisible();

  await page.locator('button.nav-item[data-view="contracts"]').click();
  await settle(page);
  await expect(page.locator("main h1")).toHaveText("Contracts");
  await page.locator('[data-action="contract-scope"][data-scope-level="domain"]').click();
  await settle(page);
  await expect(page.locator('[data-action="contract-scope"].active')).toHaveText("Sales domain");
  await page.locator('[data-action="contract-scope"][data-scope-level="project"]').click();
  await settle(page);
  await expect(page.locator('[data-action="contract-scope"].active')).toHaveText("Orders project");
  await page.locator('[data-action="propose-contract"]').click();
  await expect(page.locator("#contract-editor-json")).toBeVisible();
  await page.locator('[data-modal-close].modal-close').click();

  await page.locator('button.nav-item[data-view="policies"]').click();
  await settle(page);
  await page.locator('[data-action="policy-scope"][data-scope-level="domain"]').click();
  await settle(page);
  await expect(page.locator(".scope-summary")).toContainText("domain · sales");
  await page.locator('[data-action="view-policy"]').first().click();
  await expect(page.locator("#policy-editor-text")).toBeVisible();
  await page.locator('[data-action="validate-policy"]').click();
  await expect(page.locator(".toast", { hasText: "Cedar validation passed" })).toBeVisible();
  await page.locator('[data-modal-close].modal-close').click();

  expect(browserErrors, browserErrors.join("\n")).toEqual([]);

  await page.locator("#top-avatar").click();
  await page.locator("#login-user").selectOption("sara.sales@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();
  await page.locator('button.nav-item[data-view="workloads"]').click();
  await settle(page);
  await expect(page.locator(".workload-card")).toHaveCount(1);
  await page.locator('button.nav-item[data-view="home"]').click();
  await page.locator(".workspace-button").click();
  await expect(page.locator(".workspace-choice-list")).toContainText("Orders project");
  await expect(page.locator(".workspace-choice-list")).toContainText("Claims project");
  await page.locator(".modal-close").click();
  await page.locator('button.nav-item[data-view="contracts"]').click();
  await settle(page);
  await page.locator('[data-action="contract-scope"][data-scope-level="domain"]').click();
  await settle(page);
  await expect(page.locator("main")).toContainText("Review only");
  await expect(page.locator('[data-action="propose-contract"]')).toHaveCount(0);
  await page.locator("#top-avatar").click();

  await page.locator("#login-user").selectOption("oliver.orders@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();
  await page.locator('button.nav-item[data-view="workloads"]').click();
  await settle(page);
  await expect(page.locator(".workload-card")).toHaveCount(1);
  await expect(page.locator(".workload-card")).toContainText("customer_orders");
  await expect(page.locator(".workload-card")).not.toContainText("claims");
  await page.locator('button.nav-item[data-view="home"]').click();
  await page.locator(".workspace-button").click();
  await expect(page.locator(".workspace-choice")).toContainText("Orders project");
  await expect(page.locator(".workspace-choice")).not.toContainText("Claims project");
  await page.locator(".modal-close").click();
  const crossProjectStatus = await page.evaluate(async () => {
    const response = await fetch("/api/v1/contracts?workload=customer_orders&domain=sales&project=claims", {
      headers: { "x-adop-actor": "oliver.orders@example.com" },
    });
    return response.status;
  });
  expect(crossProjectStatus).toBe(403);
  await page.locator('button.nav-item[data-view="contracts"]').click();
  await settle(page);
  await expect(page.locator('[data-action="contract-scope"][data-scope-level="domain"]')).toHaveCount(0);
  await expect(page.locator('[data-action="contract-scope"][data-scope-level="project"]')).toHaveText("Orders project");
  await expect(page.locator("main")).toContainText("Propose project change");
  await expect(page.locator('[data-action="propose-contract"]')).toHaveCount(1);
  await page.locator('[data-action="propose-contract"]').click();
  await page.locator('[data-action="validate-contract"]').click();
  await expect(page.locator(".toast", { hasText: "Contract format is valid" })).toBeVisible();
  await page.locator('[data-modal-close].modal-close').click();
  await page.locator("#top-avatar").click();

  await page.locator("#login-user").selectOption("lina.claims@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();
  await page.locator('button.nav-item[data-view="workloads"]').click();
  await settle(page);
  await expect(page.locator(".workload-card")).toHaveCount(0);
  await expect(page.locator(".empty-state")).toContainText("No eligible workloads");
  await page.locator("#top-avatar").click();
  await expect(page.getByRole("heading", { name: "Sign in to ADOP" })).toBeVisible();
});

test("H Cherian local test identity can sign in", async ({ page }) => {
  await page.goto(baseURL, { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Sign in to ADOP" })).toBeVisible();
  await page.locator("#login-user").selectOption("hcherian@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();
  await expect(page.locator(".user-card")).toContainText("H Cherian");
  await expect(page.locator(".user-card")).toContainText("Organization admin");
  // Workspace memberships live on the Access page (Home is tabbed: Overview / Approvals / Health).
  await page.locator('button.nav-item[data-view="access"]').click();
  await expect(page.locator(".workspace-access-panel")).toContainText("Orders project");
  await expect(page.locator(".workspace-access-panel")).toContainText("Claims project");
});

test("organization admin can review and approve an API-backed policy proposal", async ({ page }) => {
  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.locator("#login-user").selectOption("hcherian@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();

  const changeId = await page.evaluate(async () => {
    // Two-person rule: Maya authors the proposal so the signed-in H Cherian can approve it.
    const headers = {
      "content-type": "application/json",
      "x-adop-actor": "maya.chen@example.com",
      "x-adop-name": "Maya Chen",
      "x-adop-role": "org-admin",
      "x-adop-workspace": "organization/default",
    };
    const policyId = "agent_authorization%2Fglobal_protection";
    const currentResponse = await fetch(`/api/v1/policies/${policyId}?scope=organization&scope_name=default`, { headers });
    const current = await currentResponse.json();
    const proposalResponse = await fetch(`/api/v1/policies/${policyId}/proposals`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        content: current.content,
        scope: "organization",
        scope_name: "default",
      }),
    });
    if (proposalResponse.ok) return (await proposalResponse.json()).change_id;
    const changes = await fetch("/api/v1/changes", { headers }).then(response => response.json());
    return changes.items.find(item =>
      item.policy_id === "agent_authorization/global_protection" &&
      item.scope === "organization" &&
      item.scope_name === "default" &&
      item.status === "pending_approval" &&
      item.created_by !== "hcherian@example.com",
    )?.change_id;
  });
  expect(changeId).toBeTruthy();

  await page.locator('button.nav-item[data-view="approvals"]').click();
  await expect(page.locator(`[data-action="review-change"][data-change-id="${changeId}"]`)).toBeVisible();
  await page.locator(`[data-action="review-change"][data-change-id="${changeId}"]`).click();
  await expect(page.getByRole("heading", { name: "Review change" })).toBeVisible();
  page.on("dialog", dialog => dialog.accept("Chromium approval test"));
  await page.locator(`[data-action="decide-change"][data-change-id="${changeId}"][data-decision="approve"]`).click();
  await expect(page.locator(".toast")).toContainText("Change approved");
});

test("organization admin can review access and switch workspaces", async ({ page }) => {
  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.locator("#login-user").selectOption("hcherian@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();

  await page.locator(".workspace-button").click();
  await expect(page.getByRole("dialog", { name: "Switch workspace" })).toBeVisible();
  await page.locator('[data-action="select-workspace"][data-workspace-name="claims"]').click();
  await expect(page.locator("#workspace-name")).toHaveText("Claims project");
  await expect(page.locator("#workspace-subtitle")).toContainText("project/claims");

  await page.locator('button.nav-item[data-view="home"]').click();
  await expect(page.locator("main")).toContainText("No workload in this workspace");
  await page.locator('button.nav-item[data-view="workloads"]').click();
  await expect(page.locator("main")).toContainText("No eligible workloads");
  await page.locator('button.nav-item[data-view="runs"]').click();
  await expect(page.locator("main")).not.toContainText("customer_orders");
  await page.locator('button.nav-item[data-view="contracts"]').click();
  await expect(page.locator("main")).toContainText("No contract in this workspace");
  await page.locator('button.nav-item[data-view="approvals"]').click();
  await expect(page.locator("main")).not.toContainText("customer_orders");

  await page.locator('button.nav-item[data-view="access"]').click();
  await expect(page.locator("main h1")).toHaveText("Access management");
  await expect(page.locator(".access-user-list")).toContainText("H Cherian");
  await expect(page.locator(".permission-grid")).toContainText("Connector administrator");
});

test("project users receive soft-isolated navigation", async ({ page }) => {
  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.locator("#login-user").selectOption("oliver.orders@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();
  await expect(page.locator('button.nav-item[data-view="access"]')).toBeHidden();
  await page.locator(".workspace-button").click();
  await expect(page.getByRole("dialog", { name: "Switch workspace" })).toContainText("Orders project");
  await expect(page.getByRole("dialog", { name: "Switch workspace" })).not.toContainText("Claims project");
});

test("generic OIDC login supports an Okta-style provider hint", async ({ page }) => {
  await page.route("**/api/v1/auth/config", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      mode: "oidc",
      provider: "Okta",
      client_id: "adop-browser-test",
      authorize_url: "https://sso.example.test/oauth2/default/v1/authorize",
      token_url: "https://sso.example.test/oauth2/default/v1/token",
      redirect_uri: `${baseURL}/`,
      provider_hint: "Okta",
    }),
  }));
  await page.route("**/api/v1/auth/me", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ authenticated: false, identity: null }),
  }));
  await page.route("https://sso.example.test/**", route => route.fulfill({
    status: 200,
    contentType: "text/html",
    body: "<title>Mock Okta sign-in</title>",
  }));

  await page.goto(baseURL, { waitUntil: "networkidle" });
  await expect(page.getByText("Continue with SSO")).toBeVisible();
  const authorizeRequest = page.waitForRequest(request =>
    request.url().startsWith("https://sso.example.test/oauth2/default/v1/authorize"),
  );
  await page.getByRole("button", { name: "Continue with SSO" }).click();
  const request = await authorizeRequest;
  const authorizeUrl = new URL(request.url());
  expect(authorizeUrl.searchParams.get("identity_provider")).toBe("Okta");
  expect(authorizeUrl.searchParams.get("code_challenge_method")).toBe("S256");
  expect(authorizeUrl.searchParams.get("response_type")).toBe("code");
});
