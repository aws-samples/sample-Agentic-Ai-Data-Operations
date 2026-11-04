const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: ".",
  testMatch: "chromium*.spec.js",
  timeout: 30_000,
  reporter: [["line"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "python3 -m api.local_server --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/api/v1/health",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
