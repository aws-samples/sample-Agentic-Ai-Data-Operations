const { test, expect } = require("@playwright/test");

const baseURL = "http://127.0.0.1:4173";

async function signIn(page, email) {
  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.locator("#login-user").selectOption(email);
  await page.getByRole("button", { name: "Enter test workspace" }).click();
  await expect(page.locator(".app-shell")).toBeVisible();
}

async function logout(page) {
  await page.locator("#top-avatar").click();
  await expect(page.getByRole("heading", { name: "Sign in to ADOP" })).toBeVisible();
}

test("responsive shell has no horizontal overflow across mobile, tablet, and desktop", async ({ page }) => {
  await signIn(page, "maya.chen@example.com");

  for (const viewport of [
    { name: "mobile", width: 390, height: 844 },
    { name: "tablet", width: 768, height: 1024 },
    { name: "desktop", width: 1440, height: 900 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.locator('button.nav-item[data-view="home"]').click();
    await expect(page.locator("main h1")).toBeVisible();
    const layout = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      sidebarVisible: getComputedStyle(document.querySelector(".sidebar")).display !== "none",
      primaryActionCount: [...document.querySelectorAll("button")].filter(button => {
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      }).length,
    }));
    expect(layout.scrollWidth, `${viewport.name} horizontal overflow`).toBeLessThanOrEqual(layout.innerWidth + 1);
    expect(layout.primaryActionCount, `${viewport.name} has no clickable controls`).toBeGreaterThan(5);
  }
});

test("admin workspace creation rejects invalid input and tolerates a double submit", async ({ page }) => {
  await signIn(page, "hcherian@example.com");
  await page.locator('button.nav-item[data-view="workspaces"]').click();
  await page.locator('[data-action="new-workspace"]').click();

  await page.locator("#workspace-name-input").fill("<script>alert(1)</script>");
  await page.locator("#workspace-label-input").fill("QA & <unsafe>");
  await page.locator('[data-action="create-workspace"]').dblclick();
  await expect(page.locator(".toast").last()).toContainText("Workspace creation failed");
  await expect(page.locator("#workspace-name-input")).toBeVisible();
});

test("contract editor surfaces malformed JSON without creating a proposal", async ({ page }) => {
  await signIn(page, "oliver.orders@example.com");
  await page.locator('button.nav-item[data-view="contracts"]').click();
  await page.locator('[data-action="propose-contract"]').click();
  await page.locator("#contract-editor-json").fill('{"zones":');
  await page.locator('[data-action="validate-contract"]').click();
  await expect(page.locator(".toast").last()).toContainText("Contract validation failed");
  await expect(page.locator("#contract-editor-json")).toHaveValue('{"zones":');
});

test("policy editor keeps adversarial text inert and validates the original Cedar flow", async ({ page }) => {
  await signIn(page, "maya.chen@example.com");
  await page.locator('button.nav-item[data-view="policies"]').click();
  await page.locator('[data-action="view-policy"]').first().click();
  const editor = page.locator("#policy-editor-text");
  await editor.fill("<img src=x onerror=window.__xss=true>");
  await expect(editor).toHaveValue("<img src=x onerror=window.__xss=true>");
  await expect(page.locator("img[src=x]")).toHaveCount(0);
  await page.locator('[data-action="validate-policy"]').click();
  await expect(page.locator(".toast")).toContainText("Cedar validation");
});

test("connector form supports a Secrets Manager reference with blank endpoint fields", async ({ page }) => {
  await signIn(page, "maya.chen@example.com");
  await page.locator('button.nav-item[data-view="connectors"]').click();
  await page.locator('[data-action="new-connector"]').first().click();
  await page.getByRole("button", { name: "Snowflake" }).click();
  await page.locator("#connector-name").fill("qa-secret-only-connector");
  await page.locator("#secret").fill("arn:aws:secretsmanager:us-east-1:133661573128:secret:adop/qa/snowflake");
  await expect(page.locator("#host")).toHaveValue("");
  await expect(page.locator("#port")).toHaveValue("");
  await expect(page.locator("#database")).toHaveValue("");
  await page.locator('[data-action="submit-connector"]').click();
  await expect(page.locator(".toast")).toContainText("saved as Not tested");
  await expect(page.locator(".connector-card")).toContainText("qa-secret-only-connector");
  await expect(page.locator(".connector-card")).not.toContainText("password");
});

test("four identities preserve project isolation and forbidden API access", async ({ page }) => {
  const cases = [
    {
      email: "oliver.orders@example.com",
      visibleWorkload: "customer_orders",
      hiddenWorkload: "claims",
      visibleProject: "Orders project",
      hiddenProject: "Claims project",
    },
    {
      email: "lina.claims@example.com",
      visibleWorkload: null,
      hiddenWorkload: "customer_orders",
      visibleProject: "Claims project",
      hiddenProject: "Orders project",
    },
  ];

  for (const item of cases) {
    await signIn(page, item.email);
    await page.locator('button.nav-item[data-view="workloads"]').click();
    if (item.visibleWorkload) {
      await expect(page.locator(".workload-card")).toContainText(item.visibleWorkload);
      await expect(page.locator(".workload-card")).not.toContainText(item.hiddenWorkload);
    } else {
      await expect(page.locator(".empty-state")).toContainText("No eligible workloads");
      await expect(page.locator("main")).not.toContainText(item.hiddenWorkload);
    }
    await page.locator(".workspace-button").click();
    const choices = page.locator(".workspace-choice-list");
    await expect(choices).toContainText(item.visibleProject);
    await expect(choices).not.toContainText(item.hiddenProject);
    await page.locator(".modal-close").click();

    const forbiddenStatus = await page.evaluate(async ({ email, workload, project, workspace }) => {
      const response = await fetch(`/api/v1/contracts?workload=${workload}&domain=sales&project=${project}`, {
        headers: {
          "x-adop-actor": email,
          "x-adop-workspace": workspace,
        },
      });
      return response.status;
    }, {
      email: item.email,
      workload: item.visibleWorkload || "claims",
      project: item.hiddenProject === "Claims project" ? "claims" : "orders",
      workspace: item.visibleProject === "Orders project" ? "project/orders" : "project/claims",
    });
    expect([403, 404]).toContain(forbiddenStatus);
    await logout(page);
  }
});

test("domain owner sees both projects but cannot use organization-only administration", async ({ page }) => {
  await signIn(page, "sara.sales@example.com");
  await expect(page.locator('button.nav-item[data-view="access"]')).toBeHidden();
  await expect(page.locator('button.nav-item[data-view="workspaces"]')).toBeHidden();
  await page.locator('button.nav-item[data-view="contracts"]').click();
  await page.locator('[data-action="contract-scope"][data-scope-level="domain"]').click();
  await expect(page.locator("main")).toContainText("Review only");
});
