import { Page, Route } from "@playwright/test";
import { mockAddons, mockSpecs } from "./addons";
import type { MRDetail, Mce, Problem, ErrorCode } from "../../types";

// Shapes follow the services' Pydantic schemas (apps/day1-service/.../api/v1/schemas.py,
// apps/day2-service/.../api/v1/schemas.py), typed so a shape change fails `tsc`.

/** A Wingman MR as the services return it (`MRDetail`). */
export function mockMR(overrides: Partial<MRDetail> = {}): MRDetail {
  return {
    iid: 42,
    project_id: 7,
    title: "[Wingman/Day1] Create cluster ocp4-prod-test-site1",
    description: "Created via Wingman",
    author: { username: "qa-admin", name: "qa-admin", avatar_url: "" },
    state: "opened",
    created_at: "2026-11-07T10:00:00+00:00",
    updated_at: "2026-11-07T10:00:00+00:00",
    merged_at: null,
    web_url: "https://gitlab.example.com/gitops-day1/platform-config/-/merge_requests/42",
    source_branch: "wingman/create-cluster-ocp4-prod-test-site1",
    target_branch: "main",
    labels: ["wingman"],
    repo: "day1",
    has_conflicts: false,
    sha: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
    ...overrides,
  };
}

/** An RFC 9457 problem body (`application/problem+json`). */
export function problemBody(
  status: number,
  code: ErrorCode,
  detail: string,
  details: Problem["details"] = {}
): Problem {
  return {
    type: `/problems/${code.toLowerCase().replace(/_/g, "-")}`,
    title: code.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
    status,
    detail,
    instance: "/api/test",
    code,
    request_id: "req_e2e0000000000001",
    details,
  };
}

/** Answer a route with a problem. */
export function fulfillProblem(
  route: Route,
  status: number,
  code: ErrorCode,
  detail: string,
  details: Problem["details"] = {}
) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify(problemBody(status, code, detail, details)),
  });
}

export function mockMce(overrides: Partial<Mce> = {}): Mce {
  return {
    name: "ocp4-prod-mce-site1-a",
    site: "site1",
    env: "prod",
    letter: "a",
    follows_convention: true,
    naming_problems: [],
    default_mastertag: "4.16.27-x86_64",
    hub_version: "4.16.27-x86_64",
    cluster_count: 0,
    stray_files: [],
    problems: [],
    ...overrides,
  };
}

export const mockMces: Mce[] = [
  mockMce(),
  mockMce({ name: "ocp4-prep-mce-site1-a", env: "prep", default_mastertag: "4.20.9-x86_64", hub_version: "4.20.9-x86_64" }),
  mockMce({ name: "ocp4-prod-mce-site2-a", site: "site2" }),
];

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

/**
 * Inject a fake authenticated admin user into localStorage/cookie so the app
 * doesn't redirect to /login.  Must be called before page.goto().
 *
 * IMPORTANT: After calling this, you must navigate to "/" first to establish
 * auth state, then navigate to your target page.  Direct navigation to a
 * sub-route may fail because Zustand's persist hydration is asynchronous.
 *
 * Usage:
 *   await injectAdminAuth(page);
 *   // ... register your route mocks ...
 *   await page.goto("/");           // establish auth
 *   await page.goto("/approvals");  // now navigate to target
 */
export async function injectAdminAuth(page: Page, username = "test-admin") {
  // Route the auth config check so it doesn't 401
  await page.route("**/api/auth/config", (route: Route) =>
    json(route, { authorize_url: "/login", dev_auth_enabled: false })
  );

  // Pre-seed localStorage with a persisted auth state that Zustand will hydrate
  await page.addInitScript((name: string) => {
    // Clear any stale query cache that could interfere with fresh test state
    localStorage.removeItem("wingman-query-cache");

    const authState = {
      state: {
        user: {
          username: name,
          groups: ["wingman-admins"],
          uid: name,
          full_name: "Test Admin",
          role: "admin",
        },
        isAuthenticated: true,
      },
      version: 0,
    };
    localStorage.setItem("wingman-auth", JSON.stringify(authState));

    // Set a fake token cookie so the API client includes it in requests
    document.cookie = "wingman-token=fake-e2e-token; path=/; SameSite=Strict";
  }, username);
}

/**
 * Mock every API the dashboard calls so that navigating to "/" doesn't cause
 * 401s that would redirect to login during auth establishment.
 */
export async function mockDashboardApis(page: Page) {
  await page.route("**/api/day1/clusters", (route: Route) => json(route, []));
  await page.route("**/api/day1/clusters/drift-summary", (route: Route) => json(route, []));
  await page.route("**/api/day1/clusters/bulk-status", (route: Route) => json(route, {}));
  await page.route("**/api/day1/specs", (route: Route) => json(route, []));
  await page.route("**/api/day1/approvals", (route: Route) => json(route, []));
  await page.route("**/api/day2/approvals", (route: Route) => json(route, []));
}

export async function mockDay2Api(page: Page) {
  await page.route("**/api/day2/addons", (route: Route) => json(route, mockAddons));

  await page.route("**/api/day2/addons/*/**", async (route: Route) => {
    const url = route.request().url();
    const match = url.match(/\/api\/day2\/addons\/([^/]+)\/([^/?]+)(\/values)?/);
    if (match) {
      const [, team, name, values] = match;
      const addon = mockAddons.find((a) => a.team === team && a.name === name);
      if (values) {
        // Helm chart defaults; the configure dialog deep-merges the team's
        // default_values on top, so an empty chart means "team values only".
        await json(route, {});
        return;
      }
      if (addon) {
        await json(route, addon);
        return;
      }
    }
    await fulfillProblem(route, 404, "NOT_FOUND", "no such addon");
  });
}

export async function mockDay1Api(page: Page) {
  await page.route("**/api/day1/specs", async (route: Route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      await json(route, mockMR({ repo: "specs", iid: 5, title: `[Wingman/Specs] Create spec ${body?.metadata?.name}` }), 201);
    } else {
      await json(route, mockSpecs);
    }
  });

  await page.route("**/api/day1/specs/*", async (route: Route) => {
    const method = route.request().method();
    const name = new URL(route.request().url()).pathname.split("/").pop();
    const spec = mockSpecs.find((s) => s.metadata.name === name);

    if (method === "GET" && spec) {
      await json(route, spec);
    } else if ((method === "PUT" || method === "DELETE") && spec) {
      await json(route, mockMR({ repo: "specs", iid: 6, title: `[Wingman/Specs] Update spec ${name}` }));
    } else {
      await fulfillProblem(route, 404, "NOT_FOUND", `spec '${name}' does not exist`);
    }
  });

  // Registered after the "specs/*" catch-all so these win (Playwright matches LIFO)
  await page.route("**/api/day1/specs/template", (route: Route) =>
    json(route, "# cluster-template.j2\nmastertag: {{ openshift_release_version }}")
  );

  await page.route("**/api/day1/specs/template/schema**", (route: Route) =>
    json(route, [
      { name: "nodepools_count", type: "integer", required: true, default: 1 },
      { name: "cluster_name", type: "string", required: true },
    ])
  );

  // GET /mces[?site=]: every MCE, or one site's
  await page.route(/\/api\/day1\/mces(\?.*)?$/, (route: Route) => {
    const site = new URL(route.request().url()).searchParams.get("site");
    return json(route, site ? mockMces.filter((m) => m.site === site) : mockMces);
  });

  await page.route("**/api/day1/sites", (route: Route) => json(route, ["site1", "site2"]));
}

export async function mockAllApis(page: Page) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await mockDay1Api(page);
  await mockDay2Api(page);
}
