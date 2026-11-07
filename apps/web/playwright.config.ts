import { defineConfig, devices } from "@playwright/test";

/**
 * Two projects:
 * - `mocked`: every spec except `live-*.spec.ts`. Every API call is
 *   intercepted (e2e/fixtures/api-handlers.ts), so no backend is needed. CI
 *   runs it (`npm run test:e2e:mocked`) against the production build.
 * - `live`: `live-*.spec.ts`, against a running stack (PLAYWRIGHT_BASE_URL).
 *
 * Without PLAYWRIGHT_BASE_URL the web app is started on :3000: `next start`
 * under CI (run `npm run build` first), `next dev` locally, reusing one that
 * is already running. PLAYWRIGHT_CHANNEL=chrome runs the tests on an
 * installed Google Chrome instead of Playwright's own Chromium.
 */
const liveBaseURL = process.env.PLAYWRIGHT_BASE_URL;
const browser = {
  ...devices["Desktop Chrome"],
  channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
};
const liveSpecs = /live-.*\.spec\.ts$/;

export default defineConfig({
  testDir: "./e2e/tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "html",
  use: {
    baseURL: liveBaseURL || "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "mocked", testIgnore: liveSpecs, use: browser },
    { name: "live", testMatch: liveSpecs, use: browser },
  ],
  webServer: liveBaseURL
    ? undefined
    : {
        command: process.env.CI ? "npm run start" : "npm run dev",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
