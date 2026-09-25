import { defineConfig, devices } from "@playwright/test";

// End-to-end checks run against a real backend (API + embedded worker, fresh SQLite database,
// mock provider enabled, default local-only auth) serving the built frontend on one origin.
const port = Number(process.env.E2E_PORT ?? 8799);
const dataDir = `.e2e-data/${Date.now()}`;

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] },
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, grepInvert: /@mobile/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
  webServer: {
    command: `uv run benchserver dev --port ${port}`,
    cwd: "..",
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ST_DATA_DIR: dataDir,
      ST_ENABLE_MOCK_PROVIDER: "1",
      ST_FRONTEND_DIST: "frontend/dist",
      ST_CATALOG_TTL_S: "86400",
    },
  },
});
