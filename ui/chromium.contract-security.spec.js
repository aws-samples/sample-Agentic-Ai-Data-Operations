const { test, expect } = require("@playwright/test");

const baseURL = "http://127.0.0.1:4173";

test("project user cannot override organization or domain contracts", async ({ page }) => {
  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.locator("#login-user").selectOption("oliver.orders@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();

  await page.locator('button.nav-item[data-view="contracts"]').click();
  await expect(page.locator("main h1")).toHaveText("Contracts");
  await expect(page.locator('[data-action="contract-scope"][data-scope-level="organization"]')).toHaveCount(0);
  await expect(page.locator('[data-action="contract-scope"][data-scope-level="domain"]')).toHaveCount(0);
  await expect(page.locator('[data-action="contract-scope"][data-scope-level="project"]')).toHaveText("Orders project");
  await expect(page.locator('[data-action="propose-contract"]')).toHaveCount(1);
  await page.locator('[data-action="propose-contract"]').click();
  await expect(page.locator("#contract-editor-json")).toBeVisible();
  await page.locator('[data-action="validate-contract"]').click();
  await expect(page.locator(".toast", { hasText: "Contract format is valid" })).toBeVisible();
  await page.locator('[data-action="save-contract-proposal"]').click();
  await expect(page.locator(".toast", { hasText: "Contract proposal saved for project/orders" })).toBeVisible();

  const results = await page.evaluate(async () => {
    const headers = {
      "content-type": "application/json",
      "x-adop-actor": "oliver.orders@example.com",
      "x-adop-name": "Oliver Orders",
      "x-adop-role": "project-user",
      "x-adop-workspace": "project/orders",
    };
    const post = async (payload) => {
      const response = await fetch("/api/v1/contracts/proposals", {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      return { status: response.status, body: await response.json() };
    };
    const organization = await post({
      workload_name: "customer_orders",
      content: { scope: "organization", zones: {} },
      scope: "organization",
      scope_name: "default",
      domain: "sales",
      project: "orders",
    });
    const domain = await post({
      workload_name: "customer_orders",
      content: { scope: "domain", zones: {} },
      scope: "domain",
      scope_name: "sales",
      domain: "sales",
      project: "orders",
    });
    const mismatchedProject = await post({
      workload_name: "customer_orders",
      content: { scope: "project", zones: {} },
      scope: "project",
      scope_name: "orders",
      domain: "finance",
      project: "orders",
    });
    const crossProject = await fetch(
      "/api/v1/contracts?workload=customer_orders&domain=sales&project=claims",
      { headers },
    );
    const visible = await fetch(
      "/api/v1/contracts?workload=customer_orders&domain=sales&project=orders",
      { headers },
    );
    return {
      organization,
      domain,
      mismatchedProject: {
        status: mismatchedProject.status,
        code: mismatchedProject.body?.error?.code,
      },
      crossProject: {
        status: crossProject.status,
        body: await crossProject.json(),
      },
      visible: {
        status: visible.status,
        body: await visible.json(),
      },
    };
  });

  expect(results.organization.status).toBe(403);
  expect(results.organization.body.error.code).toBe("contract_scope_forbidden");
  expect(results.domain.status).toBe(403);
  expect(results.domain.body.error.code).toBe("contract_scope_forbidden");
  expect(results.mismatchedProject.status).toBe(403);
  expect(results.mismatchedProject.code).toBe("scope_forbidden");
  expect(results.crossProject.status).toBe(403);
  expect(results.crossProject.body.error.code).toBe("scope_forbidden");
  expect(results.visible.status).toBe(200);
  expect(results.visible.body.proposals["project/orders"]).toBeTruthy();
});
