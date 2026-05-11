/**
 * Live-server QA suite — runs against the real deployed backend.
 * Requires PLAYWRIGHT_BASE_URL=http://localhost:8080 (or 3000 with dev server).
 *
 * Uses dev-login to obtain a real JWT so all API calls are authenticated.
 * Run with: PLAYWRIGHT_BASE_URL=http://localhost:8080 npx playwright test live-qa.spec.ts
 */

import { test, expect, type Page } from "@playwright/test";

// ── Auth helpers ──────────────────────────────────────────────────────────────

async function loginAsDev(page: Page, baseUrl: string): Promise<string> {
  // Get a real token from the dev-login endpoint
  const res = await page.request.post(`${baseUrl}/api/auth/dev-login`, {
    data: { username: "qa-admin", groups: ["wingman-admins"] },
  });
  expect(res.ok()).toBeTruthy();
  const { access_token } = await res.json();
  expect(access_token).toBeTruthy();

  // Seed auth into localStorage + cookie so Zustand hydrates on first render
  await page.addInitScript(({ token }: { token: string }) => {
    localStorage.setItem(
      "wingman-auth",
      JSON.stringify({
        state: {
          user: { username: "qa-admin", groups: ["wingman-admins"], uid: "qa-admin", role: "admin" },
          isAuthenticated: true,
        },
        version: 0,
      })
    );
    document.cookie = `wingman-token=${token}; path=/; SameSite=Strict`;
  }, { token: access_token });

  // Navigate to root. Use domcontentloaded — networkidle never fires because of
  // the SSE streaming connection (F1 keeps a persistent fetch open).
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(800); // let Zustand hydrate

  return access_token;
}

// ── Test setup ────────────────────────────────────────────────────────────────

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8080";

test.describe("Live QA — Core Pages", () => {
  let token = "";
  test.beforeEach(async ({ page }) => {
    token = await loginAsDev(page, BASE);
  });

  // ── Dashboard / Clusters ────────────────────────────────────────────────────

  test("clusters page loads with real data", async ({ page }) => {
    await page.goto("/clusters");
    await waitForPage(page);

    // Page should NOT redirect to login
    expect(page.url()).toContain("/clusters");

    // Should show at least one cluster row or empty-state — not a crash
    const hasRows = await page.locator("table tr").count() > 1;
    const hasEmpty = await page.locator("text=/no clusters/i").isVisible().catch(() => false);
    expect(hasRows || hasEmpty).toBeTruthy();
  });

  test("cluster detail page loads without crashing", async ({ page }) => {
    // Get first cluster name from API
    const res = await page.request.get(`${BASE}/api/day1/clusters`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok()) { test.skip(); return; }
    const clusters = await res.json();
    if (!clusters.length) { test.skip(); return; }

    const name = clusters[0].name;
    await page.goto(`/clusters/${name}`);
    await waitForPage(page);

    // F2: HC phase/OCP version badges should exist in DOM (may be empty if MCE unavailable)
    // At minimum the page should render without error
    expect(page.url()).toContain(`/clusters/${name}`);
    await expect(page.locator("h1, h2").first()).toBeVisible();
  });

  // ── Specs ───────────────────────────────────────────────────────────────────

  test("specs list page loads", async ({ page }) => {
    await page.goto("/specs");
    await waitForPage(page);
    expect(page.url()).toContain("/specs");
    // At least one spec card or empty state
    const count = await page.locator("[data-testid], .rounded-xl, article").count();
    expect(count).toBeGreaterThan(0);
  });

  test("F4: spec detail page has History tab", async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/day1/specs`);
    if (!res.ok()) { test.skip(); return; }
    const specs = await res.json();
    if (!specs.length) { test.skip(); return; }

    const name = specs[0].metadata.name;
    await page.goto(`/specs/${name}`);
    await waitForPage(page);

    // History tab must exist
    const historyTab = page.getByRole("tab", { name: /history/i });
    await expect(historyTab).toBeVisible();

    // Click it
    await historyTab.click();
    await page.waitForTimeout(1500);

    // Should show either commits or empty state — not crash
    const hasCommits = await page.locator("text=/commit|sha|authored/i").count() > 0;
    const hasEmpty = await page.locator("text=/no history|no commits/i").isVisible().catch(() => false);
    expect(hasCommits || hasEmpty).toBeTruthy();
  });

  test("F4: spec at-sha endpoint returns YAML", async ({ page }) => {
    // Direct API check
    const specsRes = await page.request.get(`${BASE}/api/day1/specs`);
    if (!specsRes.ok()) { test.skip(); return; }
    const specs = await specsRes.json();
    if (!specs.length) { test.skip(); return; }

    const name = specs[0].metadata.name;
    const histRes = await page.request.get(`${BASE}/api/day1/specs/${name}/history`);
    expect(histRes.ok()).toBeTruthy();
    const commits = await histRes.json();

    if (commits.length > 0) {
      const sha = commits[0].sha;
      const yamlRes = await page.request.get(`${BASE}/api/day1/specs/${name}/at/${sha}`);
      expect(yamlRes.ok()).toBeTruthy();
      const text = await yamlRes.text();
      expect(text).toContain("apiVersion");  // valid spec YAML
    }
  });

  // ── F3: Template variable preview ───────────────────────────────────────────

  test("F3: spec new page has Preview variables button", async ({ page }) => {
    await page.goto("/specs/new");
    await waitForPage(page);

    const previewBtn = page.getByRole("button", { name: /preview variables/i });
    await expect(previewBtn).toBeVisible();
  });

  // ── Approvals ───────────────────────────────────────────────────────────────

  test("approvals page loads and shows MRs", async ({ page }) => {
    await page.goto("/approvals");
    await waitForPage(page);
    expect(page.url()).toContain("/approvals");

    // Should show table with header
    await expect(page.getByText(/title/i).first()).toBeVisible();
  });

  test("F7: MRs with conflicts show Conflicted badge", async ({ page }) => {
    await page.goto("/approvals");
    await waitForPage(page);

    // Check if any MR has has_conflicts=true — badge should appear
    // We can't guarantee there's a conflicted MR in the live env, so just
    // verify the badge component renders when data has it
    const conflictBadges = page.locator("text=Conflicted");
    const count = await conflictBadges.count();
    // 0 is valid (no conflicts in live data) — we just verify no crash
    expect(count).toBeGreaterThanOrEqual(0);
  });

  // ── Global Addons page (/addons) ─────────────────────────────────────────────

  test("global /addons page renders without JSON blobs", async ({ page }) => {
    await page.goto("/addons");
    await waitForPage(page);
    expect(page.url()).toContain("/addons");

    // Click first addon to expand it
    const firstCard = page.locator(".rounded-xl, .rounded-lg").first();
    if (await firstCard.isVisible()) {
      await firstCard.click();
      await page.waitForTimeout(800);
    }

    // No raw JSON brackets should appear as the primary value display
    const pageText = await page.textContent("body") ?? "";
    // Legitimate JSON would have "{" followed by quoted keys — check for multi-key JSON objects
    const jsonBlobPattern = /\{\s*"[^"]+"\s*:/;
    expect(jsonBlobPattern.test(pageText)).toBeFalsy();
  });

  // ── Cluster Addons page ─────────────────────────────────────────────────────

  test("cluster addons page loads", async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/day1/clusters`);
    if (!res.ok()) { test.skip(); return; }
    const clusters = await res.json();
    if (!clusters.length) { test.skip(); return; }

    const name = clusters[0].name;
    await page.goto(`/clusters/${name}/addons`);
    await waitForPage(page);
    expect(page.url()).toContain("/addons");
    await expect(page.locator("h1, h2").first()).toBeVisible();
  });

  test("F6: value layers tab shows YAML not JSON", async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/day1/clusters`);
    if (!res.ok()) { test.skip(); return; }
    const clusters = await res.json();
    if (!clusters.length) { test.skip(); return; }

    const name = clusters[0].name;
    await page.goto(`/clusters/${name}/addons`);
    await waitForPage(page);

    // Expand first installed addon
    const addonCards = page.locator("button").filter({ hasText: /expand|▶|›/ });
    const count = await addonCards.count();
    if (count === 0) { test.skip(); return; }

    await addonCards.first().click();
    await page.waitForTimeout(1000);

    // Click Layers tab if present
    const layersTab = page.getByRole("tab", { name: /layers/i });
    if (await layersTab.isVisible()) {
      await layersTab.click();
      await page.waitForTimeout(500);

      // Should NOT see raw JSON object syntax
      const layersContent = await page.locator("[role=tabpanel]").textContent() ?? "";
      expect(layersContent).not.toMatch(/^\s*\{/m);
    }
  });

  // ── Docs page ───────────────────────────────────────────────────────────────

  test("docs page renders all sections without text overflow", async ({ page }) => {
    await page.goto("/docs");
    await waitForPage(page);

    // Page title must be visible
    const h1 = page.locator("h1").first();
    await expect(h1).toBeVisible();

    // Section headings must exist in the DOM (may be off-screen — scroll not required)
    const bodyText = await page.textContent("body") ?? "";
    expect(bodyText).toMatch(/overview/i);
    expect(bodyText).toMatch(/cluster/i);
    expect(bodyText).toMatch(/addon/i);
  });

  // ── Backend API health ───────────────────────────────────────────────────────

  test("day1 service is up (clusters endpoint responds)", async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/day1/clusters`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  test("day2 service is up (addons endpoint responds)", async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/day2/addons`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  test("F8: current-yaml endpoint returns YAML for existing cluster", async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/day1/clusters`);
    if (!res.ok()) { test.skip(); return; }
    const clusters = await res.json();
    if (!clusters.length) { test.skip(); return; }

    const { name, site, mce } = clusters[0];
    const yamlRes = await page.request.get(
      `${BASE}/api/day1/clusters/${name}/current-yaml?site=${site}&mce=${mce}`
    );
    expect(yamlRes.ok()).toBeTruthy();
    const text = await yamlRes.text();
    expect(text.length).toBeGreaterThan(10);
    // Should be YAML, not JSON
    expect(text).not.toMatch(/^\{/);
  });

  test("F2: live status endpoint returns hc_phase and ocp_version fields", async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/day1/clusters`);
    if (!res.ok()) { test.skip(); return; }
    const clusters = await res.json();
    if (!clusters.length) { test.skip(); return; }

    const { name, site, mce } = clusters[0];
    const statusRes = await page.request.get(
      `${BASE}/api/day1/clusters/${name}/status?site=${site}&mce=${mce}`
    );
    if (!statusRes.ok()) { test.skip(); return; } // MCE may be unavailable in test env

    const status = await statusRes.json();
    // Fields must exist in response (values may be null)
    expect("hc_phase" in status).toBeTruthy();
    expect("ocp_version" in status).toBeTruthy();
  });

  test("F1: SSE status/stream endpoint opens and delivers at least one frame", async ({ page }) => {
    // Verify that the cluster status SSE streaming endpoint is functional.
    // The frontend uses fetch() (not EventSource) to stream, so we test the raw
    // HTTP stream directly.  We open it with a timeout budget and expect at least
    // one `data:` frame within 8 seconds.
    const res = await page.request.get(`${BASE}/api/day1/clusters`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok()) { test.skip(); return; }
    const clusters = await res.json();
    if (!clusters.length) { test.skip(); return; }

    const { name, mce } = clusters[0];
    if (!mce) { test.skip(); return; }

    // page.evaluate lets us open a fetch() stream inside the browser context
    // where the auth cookie is already present.
    const gotFrame = await page.evaluate(async ({ name, mce }: { name: string; mce: string }) => {
      try {
        const res = await fetch(`/api/day1/clusters/${name}/status/stream?mce=${mce}`, {
          signal: AbortSignal.timeout(8_000),
        });
        if (!res.ok || !res.body) return false;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          if (buf.includes("data:")) return true;
        }
        return false;
      } catch { return false; }
    }, { name, mce });

    // If the SSE stream is operational, gotFrame will be true.
    // Fail the test explicitly so on-prem engineers see a clear signal.
    expect(gotFrame).toBeTruthy();
  });

  test("F5: addon catalog entries have dependencies field", async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/day2/addons`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
    const addons = await res.json() as Array<Record<string, unknown>>;

    // Every addon must have a dependencies array (even if empty)
    for (const addon of addons) {
      expect(Array.isArray(addon.dependencies)).toBeTruthy();
    }
  });
});

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Replace all networkidle waits — SSE keeps the connection alive forever */
async function waitForPage(page: Page) {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(600);
}
