const { test, expect } = require("@playwright/test");

const baseURL = "http://127.0.0.1:4173";

test("registers and health-checks an RDS PostgreSQL connector through the UI", async ({ page }) => {
  const required = ["ADOP_RDS_HOST", "ADOP_RDS_SECRET_ARN"];
  for (const name of required) {
    test.skip(!process.env[name], `Set ${name} for the ephemeral RDS test`);
  }

  await page.goto(baseURL, { waitUntil: "networkidle" });
  await page.locator("#login-user").selectOption("hcherian@example.com");
  await page.getByRole("button", { name: "Enter test workspace" }).click();
  await expect(page.locator(".user-card")).toContainText("H Cherian");

  await page.locator('button.nav-item[data-view="connectors"]').click();
  await page.locator('[data-action="new-connector"]').first().click();
  await page.getByRole("button", { name: "PostgreSQL / RDS" }).click();
  await page.locator("#connector-name").fill("rds_connector_e2e");
  await page.locator("#host").fill(process.env.ADOP_RDS_HOST);
  await page.locator("#port").fill(process.env.ADOP_RDS_PORT || "5432");
  await page.locator("#database").fill(process.env.ADOP_RDS_DATABASE || "adoptest");
  await page.locator("#secret").fill(process.env.ADOP_RDS_SECRET_ARN);

  await page.locator('[data-action="test-connector"]').click();
  await expect(page.locator(".toast")).toContainText("Real postgres connection passed");

  await page.locator('[data-action="submit-connector"]').click();
  await expect(page.locator(".connector-card")).toContainText("rds_connector_e2e");
  await page.locator(".connector-card", { hasText: "rds_connector_e2e" })
    .locator('[data-action="test-connector-card"]')
    .click();
  await expect(page.locator(".connector-card", { hasText: "rds_connector_e2e" })).toContainText("Healthy");

  const secretExposure = await page.locator(".connector-card", { hasText: "rds_connector_e2e" }).textContent();
  expect(secretExposure).not.toContain(process.env.ADOP_RDS_SECRET_ARN);
});
