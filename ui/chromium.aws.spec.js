const { test, expect } = require("@playwright/test");

const baseURL = process.env.ADOP_AWS_CONSOLE_URL;
const username = process.env.ADOP_AWS_TEST_USER;
const password = process.env.ADOP_AWS_TEST_PASSWORD;

test.skip(!baseURL || !username || !password, "Set ADOP_AWS_CONSOLE_URL, ADOP_AWS_TEST_USER, and ADOP_AWS_TEST_PASSWORD");

test("AWS mode signs in through Cognito and reaches the DynamoDB-backed console", async ({ page }) => {
  test.setTimeout(90_000);
  const browserErrors = [];
  page.on("console", message => {
    if (
      message.type() === "error"
      && !message.text().includes("Failed to load resource: the server responded with a status of 401")
    ) {
      browserErrors.push(`console: ${message.text()}`);
    }
  });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", request => {
    browserErrors.push(`requestfailed: ${request.url()} — ${request.failure()?.errorText}`);
  });

  await page.goto(baseURL, { waitUntil: "networkidle" });
  await expect(page).toHaveTitle("ADOP Console");
  await expect(page.getByRole("heading", { name: "Sign in to ADOP" })).toBeVisible();
  await page.getByRole("button", { name: "Continue with SSO" }).click();

  await page.waitForURL(/amazoncognito\.com\/login/, { timeout: 30_000 });
  await page.locator('input[name="username"]').last().fill(username);
  await page.locator('input[name="password"]').last().fill(password);
  await page.locator('input[type="submit"]').last().click();

  await page.waitForURL(url => url.origin === new URL(baseURL).origin && !url.searchParams.has("code"), {
    timeout: 30_000,
  });
  await expect(page.locator(".user-card")).toContainText("H Cherian");
  await expect(page.locator(".brand-name")).toHaveText("ADOP");
  await expect(page.locator("#user-role")).toContainText("Organization admin");
  await page.locator('button.nav-item[data-view="contracts"]').click();
  await expect(page.locator("main h1")).toHaveText("Contracts");
  await page.locator('button.nav-item[data-view="access"]').click();
  await expect(page.locator("main h1")).toHaveText("Access management");

  const protectedStatus = await page.evaluate(async () => {
    const session = JSON.parse(sessionStorage.getItem("adop.console.auth.session") || "null");
    const token = session?.apiToken || session?.idToken || session?.accessToken;
    const response = await fetch("/api/v1/auth/me", {
      headers: { authorization: `Bearer ${token}` },
    });
    return response.status;
  });
  expect(protectedStatus).toBe(200);
  expect(browserErrors, browserErrors.join("\n")).toEqual([]);
});
