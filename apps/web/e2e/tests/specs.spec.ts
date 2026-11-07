/**
 * Mocked spec pages against the rewritten day1 service: specs that do not
 * load, real spec drift, writes that keep what the page does not edit, and
 * RFC 9457 problems shown in full. Shapes follow
 * apps/day1-service/src/wingman_day1/api/v1/schemas.py.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { catalogEntry } from "../fixtures/addons";
import { injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { SpecEditPage } from "../pages/spec-edit.page";
import { SpecNewPage } from "../pages/spec-new.page";
import type { CatalogEntry, ErrorCode, MRDetail, SpecCluster, SpecDrift, SpecEntry } from "../../types";

// ── Mock data ────────────────────────────────────────────────────────────────

const STANDARD: SpecEntry = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: {
    name: "agent-standard",
    description: "Bare-metal workers on the Agent platform, two nodepools",
    version: "1.0.0",
    labels: { platform: "agent" },
  },
  spec: {
    day1: {
      variables: [],
      structure: { nodepools: [{ configs: [{}] }, { configs: [{}] }] },
      immutable_paths: [],
      template: "owner:\n  merkaz: \"{{ owner_merkaz }}\"\n",
      values: { owner_merkaz: "1234", platform: "kubevirt" },
    },
    day2: { addons: [{ team: "redbull", name: "cluster-roles", version: "main", overrideable: [] }] },
  },
  load_error: null,
  load_problems: [],
};

const BROKEN: SpecEntry = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: "broken-spec", description: "", version: "", labels: {} },
  spec: {
    day1: { variables: [], structure: {}, immutable_paths: [], template: "", values: {} },
    day2: { addons: [] },
  },
  load_error: "the spec is not a valid ClusterSpec",
  load_problems: [
    "metadata.version: Value error, spec version 'two words' must be one word, like 1.2.0",
    "spec.day2.addons.0.team: Field required",
  ],
};

function mr(iid: number, title: string): MRDetail {
  const now = new Date().toISOString();
  return {
    iid,
    project_id: 2,
    title,
    description: "",
    author: { username: "test-admin", name: "test-admin", avatar_url: "" },
    state: "opened",
    created_at: now,
    updated_at: now,
    merged_at: null,
    web_url: `https://gitlab.example.com/wingman/cluster-specs/-/merge_requests/${iid}`,
    source_branch: `wingman/spec/${iid}`,
    target_branch: "main",
    labels: ["wingman"],
    repo: "specs",
    has_conflicts: false,
    sha: "0123456789abcdef0123456789abcdef01234567",
  };
}

function problem(status: number, code: ErrorCode, detail: string, details: Record<string, unknown> = {}) {
  return {
    type: `/problems/${code.toLowerCase().replace(/_/g, "-")}`,
    title: code.replace(/_/g, " "),
    status,
    detail,
    instance: "/api/day1/specs",
    code,
    request_id: "req_e2e0000000000001",
    details,
  };
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: status >= 400 ? "application/problem+json" : "application/json",
    body: JSON.stringify(body),
  });

const SCHEMA = [
  { name: "owner_merkaz", type: "string", required: true, example: "1234" },
  { name: "platform", type: "string", required: false, default: "" },
];

/**
 * The problem panel with `text`. Filtered by text because Next's route
 * announcer is also `role="alert"`.
 */
const problemAlert = (page: Page, text: string) => page.getByRole("alert").filter({ hasText: text });

/** Auth, the dashboard, the spec list and the routes a test adds; then land on `path`. */
async function open(page: Page, path: string, routes: (page: Page) => Promise<void> = async () => {}) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/specs", (r) => json(r, [STANDARD, BROKEN]));
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route("**/api/day1/specs/template/schema**", (r) => json(r, SCHEMA));
  await page.route("**/api/day1/specs/agent-standard", (r) => json(r, STANDARD));
  await routes(page);
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  await page.goto(path);
  await page.waitForLoadState("domcontentloaded");
}

// ── List ─────────────────────────────────────────────────────────────────────

test.describe("Spec list", () => {
  test("lists a spec that does not load, with its problems", async ({ page }) => {
    await open(page, "/specs");

    const broken = page.getByTestId("spec-card-broken-spec");
    await expect(broken).toContainText("Does not load");
    await expect(broken).toContainText("the spec is not a valid ClusterSpec");
    await expect(broken).toContainText("spec.day2.addons.0.team: Field required");
    // No placeholder facts about an empty spec ("0 variables", "No addons", a version chip)
    await expect(broken).not.toContainText(/variables|no addons|presets/i);
    await expect(page.getByText(/1 does not load/)).toBeVisible();
  });

  test("a spec card shows its shape, presets and addons", async ({ page }) => {
    await open(page, "/specs");

    const card = page.getByTestId("spec-card-agent-standard");
    await expect(card).toContainText("1.0.0");
    await expect(card).toContainText("2 nodepools");
    await expect(card).toContainText("2 presets");
    await expect(card).toContainText("1 addon");
  });
});

// ── Detail ───────────────────────────────────────────────────────────────────

test.describe("Spec detail", () => {
  test("a spec that does not load shows every problem and can still be deleted", async ({ page }) => {
    await open(page, "/specs/broken-spec", async (p) => {
      await p.route("**/api/day1/specs/broken-spec", (r) =>
        json(r, problem(422, "VALIDATION_ERROR", "the spec is not a valid ClusterSpec", { problems: BROKEN.load_problems }), 422)
      );
    });

    const alert = problemAlert(page, "does not load");
    await expect(alert).toBeVisible();
    for (const line of BROKEN.load_problems!) await expect(alert).toContainText(line);
    await expect(page.getByRole("link", { name: /edit/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /delete/i })).toBeVisible();
  });

  test("overview shows preset values and the structure", async ({ page }) => {
    await open(page, "/specs/agent-standard");

    await expect(page.getByText("Preset values (2)")).toBeVisible();
    await expect(page.getByText("owner_merkaz")).toBeVisible();
    await expect(page.getByText("kubevirt")).toBeVisible();
    await expect(page.getByText("2 nodepools")).toBeVisible();
  });

  const CLUSTERS: SpecCluster[] = [
    { name: "ocp4-prod-a-site1", site: "site1", mce: "ocp4-prod-mce-site1-a", phase: "Unknown", state: "in_sync", is_drifted: false, error: null },
    { name: "ocp4-prod-b-site1", site: "site1", mce: "ocp4-prod-mce-site1-a", phase: "Unknown", state: "drifted", is_drifted: true, error: null },
    { name: "ocp4-prod-c-site1", site: "site1", mce: "ocp4-prod-mce-site1-a", phase: "Unknown", state: "unknown", is_drifted: null, error: "day2 did not answer: timed out" },
  ];
  const DRIFT: SpecDrift[] = CLUSTERS.map((c) => ({
    cluster: c.name, site: c.site, mce: c.mce, state: c.state, is_drifted: c.is_drifted, spec_version: "1.0.0", error: c.error,
  }));

  async function withDrift(p: Page, rows: SpecDrift[] = DRIFT, clusters: SpecCluster[] = CLUSTERS) {
    await p.route("**/api/day1/specs/agent-standard/clusters", (r) => json(r, clusters));
    await p.route("**/api/day1/specs/agent-standard/drift", (r) => json(r, rows));
  }

  test("drift tab counts each state and never shows unknown as in sync", async ({ page }) => {
    await open(page, "/specs/agent-standard", (p) => withDrift(p));
    await page.getByRole("button", { name: "Drift", exact: true }).click();

    await expect(page.getByTestId("spec-drift-count-drifted")).toContainText("1");
    await expect(page.getByTestId("spec-drift-count-unknown")).toContainText("1");
    await expect(page.getByTestId("spec-drift-count-in_sync")).toContainText("1");
    await expect(page.getByTestId("spec-drift-summary")).not.toContainText("match the spec");

    const unknown = page.getByTestId("spec-drift-ocp4-prod-c-site1");
    await expect(unknown).toContainText("Unknown");
    await expect(unknown).toContainText("day2 did not answer: timed out");
    await expect(unknown).not.toContainText("In sync");
    await expect(page.getByTestId("spec-drift-ocp4-prod-a-site1")).toContainText("In sync");
    await expect(page.getByRole("link", { name: "ocp4-prod-b-site1" })).toHaveAttribute(
      "href", "/clusters/ocp4-prod-b-site1?site=site1&mce=ocp4-prod-mce-site1-a"
    );
  });

  test("drift tab says so when every cluster matches", async ({ page }) => {
    await open(page, "/specs/agent-standard", (p) => withDrift(p, DRIFT.slice(0, 1), CLUSTERS.slice(0, 1)));
    await page.getByRole("button", { name: "Drift", exact: true }).click();

    await expect(page.getByText("The cluster matches the spec")).toBeVisible();
  });

  test("drift tab without clusters does not claim they are in sync", async ({ page }) => {
    await open(page, "/specs/agent-standard", (p) => withDrift(p, [], []));
    await page.getByRole("button", { name: "Drift", exact: true }).click();

    await expect(page.getByText("No clusters use this spec")).toBeVisible();
    await expect(page.getByText(/in sync|match the spec/i)).toHaveCount(0);
  });

  test("clusters tab shows each cluster's drift state", async ({ page }) => {
    await open(page, "/specs/agent-standard", (p) => withDrift(p));
    await page.getByRole("button", { name: /^Clusters/ }).click();

    await expect(page.getByTestId("spec-cluster-ocp4-prod-a-site1")).toContainText("In sync");
    await expect(page.getByTestId("spec-cluster-ocp4-prod-b-site1")).toContainText("Drifted");
    await expect(page.getByTestId("spec-cluster-ocp4-prod-c-site1")).toContainText("Unknown");
    await expect(page.getByTestId("spec-cluster-ocp4-prod-c-site1")).not.toContainText("In sync");
  });

  test("delete opens an MR and offers to review it", async ({ page }) => {
    let deleted = false;
    await open(page, "/specs/agent-standard", async (p) => {
      await withDrift(p);
      await p.route("**/api/day1/specs/agent-standard", (r) => {
        if (r.request().method() !== "DELETE") return json(r, STANDARD);
        deleted = true;
        return json(r, mr(7, "[Wingman/Specs] Delete spec agent-standard"));
      });
    });
    await page.getByRole("button", { name: /delete/i }).click();
    await page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();

    await expect(page.getByText("Delete MR !7 opened")).toBeVisible();
    await expect(page.getByRole("button", { name: "Review" })).toBeVisible();
    await page.waitForURL(/\/specs$/);
    expect(deleted).toBe(true);
  });
});

// ── Edit ─────────────────────────────────────────────────────────────────────

test.describe("Spec edit", () => {
  test("an update keeps what the page does not edit and sends nothing the service refuses", async ({ page }) => {
    let sent: Record<string, unknown> | null = null;
    await open(page, "/", async (p) => {
      await p.route("**/api/day1/specs/agent-standard", (r) => {
        if (r.request().method() !== "PUT") return json(r, STANDARD);
        sent = r.request().postDataJSON();
        return json(r, mr(8, "[Wingman/Specs] Update spec agent-standard"));
      });
    });
    const edit = new SpecEditPage(page);
    await edit.goto("agent-standard");

    await expect(page.getByTestId("spec-presets")).toContainText("owner_merkaz: 1234");
    await edit.versionInput.fill("1.1.0");
    await edit.reviewAndConfirm();

    await expect(page.getByText("Update MR !8 opened")).toBeVisible();
    expect(sent).not.toBeNull();
    const body = sent as unknown as SpecEntry;
    expect(body.metadata).toEqual({
      name: "agent-standard",
      description: STANDARD.metadata.description,
      version: "1.1.0",
      labels: { platform: "agent" },
    });
    expect(body.spec.day1.values).toEqual(STANDARD.spec.day1.values);
    expect(body.spec.day1.template).toBe("");
    expect(body.spec.day2.addons).toEqual(STANDARD.spec.day2.addons);
    expect(body).not.toHaveProperty("load_error");
    expect(body).not.toHaveProperty("load_problems");
  });

  test("a refused update lists every problem next to the actions", async ({ page }) => {
    const problems = [
      "metadata.version: Value error, spec version 'x y' must be one word, like 1.2.0",
      "spec.day2.addons: addons listed twice: redbull/cluster-roles",
    ];
    await open(page, "/", async (p) => {
      await p.route("**/api/day1/specs/agent-standard", (r) =>
        r.request().method() !== "PUT"
          ? json(r, STANDARD)
          : json(r, problem(422, "VALIDATION_ERROR", "the spec is not a valid ClusterSpec", { problems }), 422)
      );
    });
    const edit = new SpecEditPage(page);
    await edit.goto("agent-standard");
    await edit.descriptionInput.fill("Changed");
    await edit.reviewAndConfirm();

    await expect(page.getByRole("dialog")).toHaveCount(0);
    const alert = problemAlert(page, problems[0]);
    for (const line of problems) await expect(alert).toContainText(line);
  });

  test("an update of a spec that changed meanwhile offers a reload", async ({ page }) => {
    await open(page, "/", async (p) => {
      await p.route("**/api/day1/specs/agent-standard", (r) =>
        r.request().method() !== "PUT"
          ? json(r, STANDARD)
          : json(r, problem(409, "REVISION_CONFLICT", "spec 'agent-standard' changed since it was read (aaaaaaaa → bbbbbbbb); reload and try again"), 409)
      );
    });
    const edit = new SpecEditPage(page);
    await edit.goto("agent-standard");
    await edit.descriptionInput.fill("Changed");
    await edit.reviewAndConfirm();

    await expect(problemAlert(page, "changed since you opened it")).toBeVisible();
    await page.getByRole("button", { name: /reload spec/i }).click();
    await expect(problemAlert(page, "changed since you opened it")).toHaveCount(0);
    await expect(edit.descriptionInput).toHaveValue(STANDARD.metadata.description!);
  });

  test("a spec that does not load cannot be edited", async ({ page }) => {
    await open(page, "/", async (p) => {
      await p.route("**/api/day1/specs/broken-spec", (r) =>
        json(r, problem(422, "VALIDATION_ERROR", "the spec is not a valid ClusterSpec", { problems: BROKEN.load_problems }), 422)
      );
    });
    const edit = new SpecEditPage(page);
    await edit.goto("broken-spec");

    await expect(problemAlert(page, "cannot be edited")).toBeVisible();
    await expect(edit.reviewButton).toHaveCount(0);
  });
});

// ── Create ───────────────────────────────────────────────────────────────────

test.describe("Spec create", () => {
  async function openNew(page: Page, onPost: (route: Route) => Promise<void>, catalog: CatalogEntry[] = []) {
    await open(page, "/", async (p) => {
      await p.route("**/api/day2/addons", (r) => json(r, catalog));
      await p.route("**/api/day1/specs/template", (r) => json(r, ""));
      await p.route("**/api/day1/specs", (r) =>
        r.request().method() === "POST" ? onPost(r) : json(r, [STANDARD, BROKEN])
      );
    });
    const spec = new SpecNewPage(page);
    await spec.goto();
    await page.waitForLoadState("domcontentloaded");
    return spec;
  }

  test("an existing name says so and links the spec", async ({ page }) => {
    const spec = await openNew(page, (r) =>
      json(r, problem(409, "ALREADY_EXISTS", "spec 'agent-standard' already exists"), 409)
    );
    await spec.fillBasicInfo("agent-standard", "1.0.0");
    await spec.reviewAndConfirm();

    await expect(problemAlert(page, 'A spec named "agent-standard" already exists')).toBeVisible();
    await expect(page.getByRole("link", { name: "Open the existing spec" })).toHaveAttribute("href", "/specs/agent-standard");
  });

  test("a refused create lists every field error", async ({ page }) => {
    const spec = await openNew(page, (r) =>
      json(r, problem(422, "VALIDATION_ERROR", "The request is not valid.", {
        errors: [
          { loc: ["body", "metadata", "labels", "team"], msg: "Input should be a valid string", type: "string_type" },
          { loc: ["body", "spec", "day1", "bogus"], msg: "Extra inputs are not permitted", type: "extra_forbidden" },
        ],
      }), 422)
    );
    await spec.fillBasicInfo("new-spec", "1.0.0");
    await spec.reviewAndConfirm();

    const alert = problemAlert(page, "The request is not valid.");
    await expect(alert).toContainText("metadata.labels.team: Input should be a valid string");
    await expect(alert).toContainText("spec.day1.bogus: Extra inputs are not permitted");
  });

  test("an invalid name is flagged before anything is sent", async ({ page }) => {
    let posted = false;
    const spec = await openNew(page, async (r) => {
      posted = true;
      await json(r, mr(9, "unexpected"));
    });
    await spec.fillBasicInfo("Bad_Name", "two words");
    await spec.submit();

    await expect(page.getByText(/Lowercase letters, digits and '-', starting and ending/)).toBeVisible();
    await expect(page.getByText(/One word of letters, digits/)).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(posted).toBe(false);
  });

  test("a create sends the description and opens an MR", async ({ page }) => {
    let sent: SpecEntry | null = null;
    const spec = await openNew(page, async (r) => {
      sent = r.request().postDataJSON();
      await json(r, mr(10, "[Wingman/Specs] Create spec new-spec"), 201);
    });
    await spec.fillBasicInfo("new-spec", "2.0.0");
    await spec.descriptionInput.fill("For test clusters");
    await spec.reviewAndConfirm();

    await expect(page.getByText("Spec MR !10 opened")).toBeVisible();
    await page.waitForURL(/\/specs$/);
    expect(sent).toMatchObject({ metadata: { name: "new-spec", version: "2.0.0", description: "For test clusters" } });
  });

  test("a chart is added at its team default, HEAD when the team sets none", async ({ page }) => {
    let sent: SpecEntry | null = null;
    const spec = await openNew(
      page,
      async (r) => {
        sent = r.request().postDataJSON();
        await json(r, mr(11, "[Wingman/Specs] Create spec new-spec"), 201);
      },
      [catalogEntry({ team: "redbull", name: "cluster-roles", current_version: "HEAD", available_versions: ["main", "release-1"], default_values: {} })]
    );
    const card = spec.getAddonCard("redbull", "cluster-roles");
    await expect(card.getByRole("combobox")).toContainText("HEAD");
    await card.getByRole("combobox").click();
    // HEAD is the chart repo's default branch, which the branches list first
    await expect(page.getByRole("option")).toHaveText(["HEAD", "main", "release-1"]);
    await page.keyboard.press("Escape");

    await spec.selectAddon("redbull", "cluster-roles");
    await spec.fillBasicInfo("new-spec", "1.0.0");
    await spec.reviewAndConfirm();

    await expect(page.getByText("Spec MR !11 opened")).toBeVisible();
    expect((sent as unknown as SpecEntry).spec.day2.addons).toEqual([
      { team: "redbull", name: "cluster-roles", version: "HEAD", overrideable: [] },
    ]);
  });
});
