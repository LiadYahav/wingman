/**
 * An add-on's page on Addons (ADR-0053), mocked: its team default and fleet
 * defaults, which destinations a default deploys to
 * (exclusions, which orphan the workload), a destination's value override
 * with the effective values before and after, and its own deploy config.
 * Every write is previewed, confirmed, and sent with the preview's
 * `needs_confirmation` and `digest`; a 409 plan-changed shows the new plan
 * (docs/notes/2026-11-12-operators-page-api.md).
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { HOSTED_ID, TWIN_IDS, mockDay2World } from "../fixtures/day2";
import { READ_ONLY_REASON, TEAMS, mockAuthoring } from "../fixtures/authoring";
import {
  CERT_MANAGER_YAML,
  MCE_A,
  MCE_A_NAME,
  MCE_EXCLUDED,
  MCE_OVERRIDE,
  MCE_OVERRIDE_NAME,
  MCE_OWN,
  MCE_OWN_NAME,
  mockAddonDetail,
  type AddonRequests,
} from "../fixtures/addon-detail";

let requests: AddonRequests;

async function setUp(page: Page, options: Parameters<typeof mockAddonDetail>[1] = {}) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await mockDay2World(page);
  await mockAuthoring(page);
  requests = await mockAddonDetail(page, options);
}

const realWrites = () => requests.writes.filter((w) => !w.dryRun);
const dryRuns = () => requests.writes.filter((w) => w.dryRun);
const mces = (page: Page) => page.getByTestId("scope-mces");
const review = (page: Page) => page.getByRole("dialog").filter({ has: page.getByTestId("authoring-plan") });
const formDialog = (page: Page) => page.getByRole("dialog").filter({ has: page.getByRole("button", { name: "Preview changes" }) });

test.describe("Navigation", () => {
  test.beforeEach(async ({ page }) => setUp(page));

  test("an add-on's defaults are reached from the Addons page, and there is no Operators entry", async ({ page }) => {
    await go(page, "/");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link", { name: "Operators" })).toHaveCount(0);
    await nav.getByRole("link", { name: "Addons" }).click();
    await expect(page).toHaveURL(/\/addons$/);

    await page.getByTestId("team-platform").getByRole("button", { name: /cert-manager/ }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("link", { name: "Defaults & overrides" }).click();
    await expect(page).toHaveURL(/\/addons\/platform\/cert-manager$/);
    await expect(page.getByRole("heading", { level: 1, name: "cert-manager" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Addons");
    await expect(nav.getByRole("link", { name: "Addons" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("main")).not.toContainText(/\boperator\b|Operators/);
  });

  test("3.12.0's Operators links redirect to the Addons pages", async ({ page }) => {
    await go(page, "/operators");
    await expect(page).toHaveURL(/\/addons$/);
    await go(page, "/teams/platform/operators");
    await expect(page).toHaveURL(/\/addons\?team=platform$/);
    await expect(page.getByTestId("team-filter")).toContainText("Showing platform only");
    await expect(page.getByTestId("team-observability")).toHaveCount(0);
    await go(page, "/teams/platform/operators/cert-manager");
    await expect(page).toHaveURL(/\/addons\/platform\/cert-manager$/);
    await go(page, "/teams/platform/new-operator");
    await expect(page).toHaveURL(/\/addons\/new\?team=platform$/);
    await expect(page.getByTestId("new-addon-form")).toBeVisible();
  });

  test("an unknown add-on says so", async ({ page }) => {
    await go(page, "/addons/platform/nope");
    await expect(page.getByTestId("addon-not-found")).toContainText("platform has no add-on nope");
  });
});

test.describe("An add-on's page", () => {
  test.beforeEach(async ({ page }) => setUp(page));

  test("shows the files as written, the OCP pins, and the four scopes in order", async ({ page }) => {
    await go(page, "/addons/platform/cert-manager");
    const teamDefault = page.getByRole("region", { name: "Team default" });
    await expect(teamDefault.getByLabel("Contents of operators/cert-manager/cert-manager.yaml")).toHaveText(CERT_MANAGER_YAML.trimEnd());
    await expect(teamDefault).toContainText("https://gitlab.example.com/helm-charts/cert-manager.git");

    const scopes = page.getByRole("region", { name: "Defaults" }).locator("[data-testid^=scope-]:not([data-testid=scope-status])");
    await expect(scopes).toHaveCount(4);
    await expect(scopes.nth(0)).toHaveAttribute("data-testid", "scope-hosted-clusters");
    await expect(scopes.nth(1)).toHaveAttribute("data-testid", "scope-mces");
    await expect(scopes.nth(2)).toHaveAttribute("data-testid", "scope-hub");
    await expect(scopes.nth(3)).toHaveAttribute("data-testid", "scope-upi");
    await expect(page.getByTestId("scope-hosted-clusters").getByTestId("scope-status")).toHaveText("not a default");
    await expect(mces(page).getByTestId("scope-status")).toHaveText("a default");

    // Each destination's state, grouped by site and env.
    await expect(mces(page).getByRole("group", { name: "site1 · prep" })).toContainText(MCE_A_NAME);
    await expect(mces(page).getByTestId(`destination-${MCE_OWN_NAME}`)).toContainText("own deploy config");
    await expect(mces(page).getByRole("checkbox", { name: `Deployed by this default on ${MCE_OWN_NAME}` })).toBeDisabled();
    await expect(mces(page).getByRole("checkbox", { name: "Deployed by this default on ocp4-prep-mce-site3-d" })).toBeDisabled();
    await expect(mces(page).getByRole("checkbox", { name: `Deployed by this default on ${MCE_A_NAME}` })).toBeChecked();
    await expect(mces(page).getByRole("checkbox", { name: "Deployed by this default on ocp4-prod-mce-site1-a" })).not.toBeChecked();
    await expect(mces(page)).toContainText("ocp4-old-mce");
    await expect(page.getByTestId("unregistered-mces")).toContainText("not registered with platform, a default does not reach it");
  });

  test("an edit of the team default is confirmed and sent with the preview's digest", async ({ page }) => {
    await go(page, "/addons/platform/cert-manager");
    await page.getByRole("region", { name: "Team default" }).getByRole("button", { name: "Edit team default" }).click();
    const form = formDialog(page);
    await form.getByLabel("Contents of operators/cert-manager/values.yaml").fill("replicas: 2\n");
    await form.getByRole("button", { name: "Preview changes" }).click();

    const plan = review(page);
    await expect(plan.getByTestId(`impact-${MCE_A_NAME}`)).toContainText("replicas");
    // A key set to a Helm null deletes the chart's own default: said so, and only for that key (after_null).
    await expect(plan.getByTestId("helm-null")).toHaveCount(1);
    await expect(plan.getByTestId("helm-null")).toContainText("deletes the chart's own default");
    await expect(plan.getByRole("row", { name: /resources\.limits\.cpu/ })).toContainText("deletes the chart's own default");
    await expect(plan.getByRole("row", { name: /installCRDs/ })).not.toContainText("deletes");
    const confirm = plan.getByRole("button", { name: /Create MR/ });
    await expect(confirm).toBeDisabled();
    await plan.getByRole("checkbox", { name: `I understand the app on ${MCE_A_NAME} changes as listed` }).click();
    await confirm.click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("team default");
    expect(dryRuns()).toHaveLength(1);
    const real = realWrites()[0];
    expect(real.method).toBe("PUT");
    expect(real.path).toBe("/api/day2/addons/platform/cert-manager");
    expect(real.body).toEqual({
      ...dryRuns()[0].body,
      confirm_changes: [MCE_A],
      expected_digest: "digest-v1-update-team-default-cert-manager-",
    });
    expect(dryRuns()[0].body).toEqual({ last_commit_id: "platform-catalog-1", values: { replicas: 2 } });
  });

  test("a repo that moved since the preview shows the new plan, and only that is sent", async ({ page }) => {
    await setUp(page, { planChangedOnce: true });
    await go(page, "/addons/platform/cert-manager");
    await page.getByRole("region", { name: "Team default" }).getByRole("button", { name: "Edit team default" }).click();
    await formDialog(page).getByLabel("Contents of operators/cert-manager/values.yaml").fill("replicas: 2\n");
    await formDialog(page).getByRole("button", { name: "Preview changes" }).click();

    const plan = review(page);
    await plan.getByRole("checkbox", { name: `I understand the app on ${MCE_A_NAME} changes as listed` }).click();
    await plan.getByRole("button", { name: /Create MR/ }).click();

    // 409 plan-changed: previewed again, the new plan shown, nothing opened.
    await expect(plan.getByTestId("plan-changed")).toContainText("The repo changed since your preview");
    await expect(plan.getByTestId(`impact-${MCE_OVERRIDE_NAME}`)).toContainText("projectNamespace");
    await expect(page.getByRole("region", { name: "Opened merge requests" })).toHaveCount(0);
    const confirm = plan.getByRole("button", { name: /Create MR/ });
    await expect(confirm).toBeDisabled();
    await plan.getByRole("checkbox", { name: /I understand the apps on these 2 destinations change as listed/ }).click();
    await confirm.click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toBeVisible();
    expect(dryRuns()).toHaveLength(2);
    const [first, second] = realWrites();
    expect(first.body.expected_digest).toBe("digest-v1-update-team-default-cert-manager-");
    expect(second.body.expected_digest).toBe("digest-v2-update-team-default-cert-manager-");
    expect(second.body.confirm_changes).toEqual([MCE_A, MCE_OVERRIDE]);
  });
});

test.describe("Which destinations a default deploys to", () => {
  test.beforeEach(async ({ page }) => setUp(page));

  test("excluding one orphans its workload: the plan lists exactly it, and it must be confirmed", async ({ page }) => {
    await go(page, "/addons/platform/cert-manager");
    const preview = mces(page).getByRole("button", { name: "Preview exclusions" });
    await expect(preview).toBeDisabled();
    await mces(page).getByRole("checkbox", { name: `Deployed by this default on ${MCE_A_NAME}` }).click();
    await expect(mces(page).getByTestId("exclude-warning")).toContainText(`Excluding deletes the Application on ${MCE_A_NAME}`);
    await expect(mces(page).getByTestId(`destination-${MCE_A_NAME}`)).toContainText("will be excluded");
    await preview.click();

    const plan = review(page);
    const orphans = plan.getByTestId("orphan-warning");
    await expect(orphans).toContainText(`The Application on ${MCE_A_NAME} is deleted, and its workload keeps running.`);
    await expect(orphans.getByRole("list", { name: "Applications deleted" }).getByRole("listitem")).toHaveCount(1);
    await expect(orphans).toContainText(`platform-${MCE_A_NAME}-cert-manager-deploy`);
    await expect(plan.getByTestId("plan-title")).toHaveText(
      `[Wingman/Day2] Exclude addon platform/cert-manager from ${MCE_A_NAME} (fleet default on every MCE)`,
    );
    const confirm = plan.getByRole("button", { name: /Create MR/ });
    await expect(confirm).toBeDisabled();
    await plan.getByRole("checkbox", { name: `Delete the Application on ${MCE_A_NAME} and leave its workload running, unmanaged` }).click();
    await confirm.click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("Exclude addon platform/cert-manager");
    const real = realWrites()[0];
    expect(real.method).toBe("PUT");
    expect(real.path).toBe("/api/day2/addons/platform/cert-manager/defaults/mces/exclusions");
    expect(real.body).toEqual({
      excluded: [MCE_A, MCE_EXCLUDED, MCE_OWN],
      last_commit_id: "platform-exclusions-1",
      confirm_changes: [MCE_A],
      expected_digest: "digest-v1-set-exclusions-cert-manager-mces",
      message: null,
    });
    expect(dryRuns()[0].body).toEqual({ ...real.body, confirm_changes: [], expected_digest: null });
  });

  test("destinations that share a name are excluded together", async ({ page }) => {
    await go(page, "/addons/observability/grafana");
    const hosted = page.getByTestId("scope-hosted-clusters");
    const twins = hosted.getByRole("checkbox", { name: "Deployed by this default on twin" });
    await expect(twins).toHaveCount(2);
    await expect(hosted.getByTestId("shared-name").first()).toContainText("excluded or included together");
    await twins.first().click();
    await expect(twins.nth(0)).not.toBeChecked();
    await expect(twins.nth(1)).not.toBeChecked();
    await hosted.getByRole("button", { name: "Preview exclusions" }).click();
    const plan = review(page);
    await expect(plan.getByTestId("orphan-warning").getByRole("listitem")).toHaveCount(2);
    await plan.getByRole("checkbox", { name: `Delete the Applications on ${TWIN_IDS.join(", ")} and leave their workloads running, unmanaged` }).click();
    await plan.getByRole("button", { name: /Create MR/ }).click();
    await expect(page.getByRole("region", { name: "Opened merge requests" })).toBeVisible();
    expect(realWrites()[0].body).toMatchObject({ excluded: [HOSTED_ID, ...TWIN_IDS], confirm_changes: TWIN_IDS });
  });

  test("including one generates its app again, with nothing to confirm", async ({ page }) => {
    await go(page, "/addons/platform/cert-manager");
    await mces(page).getByRole("checkbox", { name: "Deployed by this default on ocp4-prod-mce-site1-a" }).click();
    await expect(mces(page)).toContainText("generates the app there again");
    await mces(page).getByRole("button", { name: "Preview exclusions" }).click();
    const plan = review(page);
    await expect(plan.getByTestId("impact-ocp4-prod-mce-site1-a")).toContainText("added");
    await plan.getByRole("button", { name: /Create MR/ }).click();
    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("Include addon platform/cert-manager");
    expect(realWrites()[0].body).toMatchObject({ excluded: [MCE_OWN], confirm_changes: [] });
  });
});

test.describe("A destination's overrides", () => {
  test.beforeEach(async ({ page }) => setUp(page));

  test("a value override shows the effective values before and after, and sends the file", async ({ page }) => {
    await go(page, "/addons/platform/cert-manager");
    await mces(page).getByRole("button", { name: `Add values override on ${MCE_A_NAME}` }).click();
    const form = formDialog(page);
    await expect(form.getByRole("heading", { name: `cert-manager values on ${MCE_A_NAME}` })).toBeVisible();
    await expect(form.getByTestId("before-after")).toContainText("no change");

    await form.getByRole("button", { name: "YAML", exact: true }).click();
    await form.getByLabel(`Contents of defaults/mces/cert-manager/values-${MCE_A_NAME}.yaml`).fill("replicas: 2\n");
    const replicas = form.getByTestId("effective-replicas");
    await expect(replicas).toContainText("1");
    await expect(replicas).toContainText("team");
    await expect(replicas).toContainText("2");
    await expect(replicas).toContainText("fleet · this cluster");

    // Two previews: today's (no override_values) and the edit's.
    expect(requests.previews.some((b) => b.cluster === MCE_A && !("override_values" in b))).toBe(true);
    expect(requests.previews.some((b) => b.cluster === MCE_A && JSON.stringify(b.override_values) === JSON.stringify({ replicas: 2 }))).toBe(true);

    await form.getByRole("button", { name: "Preview changes" }).click();
    const plan = review(page);
    await expect(plan).toContainText(`defaults/mces/cert-manager/values-${MCE_A_NAME}.yaml`);
    await plan.getByRole("checkbox", { name: `I understand the app on ${MCE_A_NAME} changes as listed` }).click();
    await plan.getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText(`values on ${MCE_A_NAME}`);
    const real = realWrites()[0];
    expect(real.path).toBe(`/api/day2/addons/platform/cert-manager/defaults/mces/destinations/${encodeURIComponent(MCE_A)}/values`);
    expect(real.body).toEqual({
      values: { replicas: 2 },
      last_commit_id: null,
      confirm_changes: [MCE_A],
      expected_digest: "digest-v1-override-values-cert-manager-mces",
      message: null,
    });
  });

  test("an existing override can be deleted, back to the default's values", async ({ page }) => {
    await go(page, "/addons/platform/cert-manager");
    await expect(mces(page).getByTestId(`destination-${MCE_OVERRIDE_NAME}`)).toContainText(`values-${MCE_OVERRIDE_NAME}.yaml`);
    await mces(page).getByRole("button", { name: `Edit values override on ${MCE_OVERRIDE_NAME}` }).click();
    const form = formDialog(page);
    await form.getByRole("radio", { name: /Delete it/ }).check();
    await expect(form.getByTestId("effective-replicas")).toContainText("3");
    await form.getByRole("button", { name: "Preview changes" }).click();
    const plan = review(page);
    await plan.getByRole("checkbox", { name: `I understand the app on ${MCE_OVERRIDE_NAME} changes as listed` }).click();
    await plan.getByRole("button", { name: /Create MR/ }).click();
    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("back to the fleet default");
    expect(realWrites()[0].body).toMatchObject({ values: null, last_commit_id: "platform-repo-1" });
  });

  test("an own deploy config sends only the keys that are set", async ({ page }) => {
    await go(page, "/addons/platform/cert-manager");
    await mces(page).getByRole("button", { name: `Set an own deploy config on ${MCE_A_NAME}` }).click();
    const form = formDialog(page);
    await expect(form).toContainText("The Application keeps its name");
    await expect(form.getByRole("button", { name: "Preview changes" })).toBeDisabled();
    await form.getByRole("textbox", { name: /Project namespace/ }).fill("certs");
    await form.getByRole("button", { name: "Preview changes" }).click();
    const plan = review(page);
    await plan.getByRole("checkbox", { name: `I understand the app on ${MCE_A_NAME} changes as listed` }).click();
    await plan.getByRole("button", { name: /Create MR/ }).click();
    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("deploy config");
    const real = realWrites()[0];
    expect(real.path).toBe(`/api/day2/addons/platform/cert-manager/defaults/mces/destinations/${encodeURIComponent(MCE_A)}/deploy`);
    expect(real.body).toEqual({
      deploy: { target_revision: null, repourl: null, path: null, project_namespace: "certs" },
      last_commit_id: "platform-repo-1",
      confirm_changes: [MCE_A],
      expected_digest: "digest-v1-override-deploy-cert-manager-mces",
      message: null,
    });
  });
});

test.describe("A read-only team", () => {
  test.beforeEach(async ({ page }) => setUp(page));

  test("offers no write, and says why", async ({ page }) => {
    await go(page, "/addons?team=security");
    const security = page.getByTestId("team-security");
    await expect(security).toContainText("read-only");
    await expect(security.getByRole("button", { name: "New add-on" })).toBeDisabled();
    await expect(security.getByRole("button", { name: "New add-on" })).toHaveAttribute("title", READ_ONLY_REASON);

    await go(page, "/addons/security/kyverno");
    await expect(page.getByRole("note").first()).toContainText(READ_ONLY_REASON);
    await expect(page.getByRole("button", { name: "Edit team default" })).toBeDisabled();
    await expect(page.getByTestId("scope-mces").getByRole("button", { name: "Edit the default on every MCE" })).toBeDisabled();
    await expect(page.getByTestId("scope-hub").getByRole("button", { name: "Make it a default" })).toBeDisabled();
    await expect(page.getByTestId("scope-mces").getByRole("checkbox").first()).toBeDisabled();
    await expect(page.getByTestId("scope-mces").getByRole("button", { name: "Preview exclusions" })).toHaveCount(0);
  });

  test("writes stay off while the team's access is unknown", async ({ page }) => {
    await setUp(page, {
      teams: TEAMS.map((t) =>
        t.name === "platform"
          ? { ...t, writable: false, access_role: "unknown", read_only_reason: "Wingman could not read platform's access to sigs/platform." }
          : t,
      ),
    });
    await go(page, "/addons/platform/cert-manager");
    await expect(page.getByRole("note").first()).toContainText("Wingman could not read platform's access");
    await expect(page.getByRole("button", { name: "Edit team default" })).toBeDisabled();
  });

  test("writes stay off when the teams list fails", async ({ page }) => {
    await page.route("**/api/day2/teams", (r) => r.fulfill({ status: 503, body: "unavailable" }));
    await go(page, "/addons/platform/cert-manager");
    // The list is retried before it fails; until then and after, writes stay off.
    await expect(page.getByRole("button", { name: "Edit team default" })).toBeDisabled();
    await expect(page.getByRole("note").first()).toContainText("Wingman could not read platform's write access yet.", { timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Edit team default" })).toBeDisabled();
  });
});
