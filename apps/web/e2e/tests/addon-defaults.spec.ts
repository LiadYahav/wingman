/**
 * An add-on's page on Addons (ADR-0053), mocked: the add-on (its deploy
 * config and Sig values) and its fleet defaults, values per env and per destination (MCEs, hosted clusters, UPI)
 * with the effective values before and after, deploying it on specific MCEs
 * (one install MR per MCE, with remove), and the hosted-clusters panel (no
 * picks: a hosted cluster's own add-ons are its flavor's).
 * No exclusion is offered (ADR-0053's amendment). Every write is previewed, confirmed, and sent with the preview's
 * `needs_confirmation` and `digest`; a 409 plan-changed shows the new plan
 * (docs/notes/2026-11-12-operators-page-api.md).
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { HOSTED_ID, HOSTED_NAME, mockDay2World } from "../fixtures/day2";
import { READ_ONLY_REASON, TEAMS, mockAuthoring } from "../fixtures/authoring";
import {
  CERT_MANAGER_YAML,
  MCE_A,
  MCE_A_NAME,
  MCE_EXCLUDED,
  MCE_EXCLUDED_NAME,
  MCE_OVERRIDE,
  MCE_OVERRIDE_NAME,
  MCE_UNREGISTERED,
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

/** Edit add-on's form once the dialog has focused its first field: text typed before can land there. */
async function editAddonForm(page: Page) {
  const form = formDialog(page);
  await expect(form.getByRole("textbox", { name: "Chart repo URL (repourl)" })).toBeFocused();
  return form;
}

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

  test("the Addons page prefetches no add-on page as it loads, and its links still navigate on the client", async ({ page }) => {
    await go(page, "/");
    const prefetched: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.searchParams.has("_rsc") && url.pathname.startsWith("/addons/")) prefetched.push(url.pathname + url.search);
    });
    await page.goto("/addons");
    const team = page.getByTestId("team-platform");
    const manage = team.getByRole("link", { name: "Manage the defaults of external-secrets" });
    await expect(team.getByRole("link", { name: "New add-on in platform" })).toBeVisible();
    await expect(manage).toBeVisible();
    // Next.js prefetches a bare <Link> as soon as it is on screen; give it the time it would take.
    await page.waitForTimeout(1_000);
    expect(prefetched).toEqual([]);

    await page.evaluate(() => Object.assign(window, { stayedOnPage: true }));
    await manage.click();
    await expect(page).toHaveURL(/\/addons\/platform\/external-secrets$/);
    await expect(page.getByRole("heading", { level: 1, name: "external-secrets" })).toBeVisible();
    expect(await page.evaluate(() => "stayedOnPage" in window)).toBe(true); // no full page load
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
    const addon = page.getByRole("region", { name: "Add-on" });
    await expect(addon.getByLabel("Contents of operators/cert-manager/cert-manager.yaml")).toHaveText(CERT_MANAGER_YAML.trimEnd());
    await expect(addon).toContainText("https://gitlab.example.com/helm-charts/cert-manager.git");
    await expect(addon.getByRole("button", { name: "Edit add-on" })).toBeEnabled();
    await addon.getByRole("tab", { name: "Sig values" }).click();
    await expect(addon.getByRole("list", { name: "Values, lowest first" }).locator("[aria-current]")).toHaveText("Sig values");
    await expect(addon.getByLabel("Contents of operators/cert-manager/values.yaml")).toBeVisible();
    await expect(page.getByRole("main")).not.toContainText(/team (default|value)/i);

    const scopes = page.getByRole("region", { name: "Defaults" }).locator("[data-testid^=scope-]:not([data-testid=scope-status])");
    await expect(scopes).toHaveCount(4);
    await expect(scopes.nth(0)).toHaveAttribute("data-testid", "scope-hosted-clusters");
    await expect(scopes.nth(1)).toHaveAttribute("data-testid", "scope-mces");
    await expect(scopes.nth(2)).toHaveAttribute("data-testid", "scope-hub");
    await expect(scopes.nth(3)).toHaveAttribute("data-testid", "scope-upi");
    await expect(page.getByTestId("scope-hosted-clusters").getByTestId("scope-status")).toHaveText("not a default");
    await expect(mces(page).getByTestId("scope-status")).toHaveText("a default");

    // Each destination's state, grouped by site and env, with its values; no exclusion is offered.
    await expect(mces(page).getByRole("group", { name: "site1 · prep" })).toContainText(MCE_A_NAME);
    await expect(mces(page).getByTestId(`destination-${MCE_OVERRIDE_NAME}`)).toContainText(`values-${MCE_OVERRIDE_NAME}.yaml`);
    await expect(mces(page).getByRole("button", { name: `Edit values override on ${MCE_OVERRIDE_NAME}` })).toBeEnabled();
    await expect(mces(page).getByRole("checkbox")).toHaveCount(0);
    await expect(mces(page).getByRole("button", { name: /exclusions|deploy config/i })).toHaveCount(0);
    // A repo's own exclusions.yaml is shown as it is, read only.
    await expect(page.getByTestId("exclusions-note")).toContainText("Wingman reads that file and does not edit it");
    // An MCE default is not also installed per MCE (the XOR rule).
    await expect(mces(page).getByTestId("deploy-on-mces-blocked")).toContainText("the XOR rule");

    // Hosted clusters, not a default here: no rows; their own add-ons are their flavor's.
    const hosted = page.getByTestId("scope-hosted-clusters");
    await expect(hosted.getByTestId("hosted-clusters-note")).toContainText("comes from its flavor and the create form");
    await expect(hosted.getByRole("link", { name: "Flavors" })).toHaveAttribute("href", "/specs");
    await expect(hosted.locator("[data-testid^=destination-]")).toHaveCount(0);
    // Values per env on the MCE default.
    await expect(mces(page).getByTestId("env-prep")).toContainText("the default's values");
  });

  test("a destination's name opens its charts page: an MCE's, in its row and where it is installed", async ({ page }) => {
    await go(page, "/addons/platform/external-secrets");
    const installedRow = mces(page).getByTestId(`installed-${MCE_EXCLUDED_NAME}`);
    await expect(installedRow.getByRole("link", { name: MCE_EXCLUDED_NAME })).toHaveAttribute(
      "href",
      `/clusters/${encodeURIComponent(MCE_EXCLUDED)}/addons`,
    );

    await go(page, "/addons/platform/cert-manager");
    await mces(page).getByTestId(`destination-${MCE_A_NAME}`).getByRole("link", { name: MCE_A_NAME }).click();
    await expect(page).toHaveURL(new RegExp(`/clusters/${encodeURIComponent(MCE_A)}/addons$`));
    // The mocked day2 world does not know this MCE: its page says so, and leads back to the add-ons.
    await expect(page.getByRole("link", { name: "Back to add-ons" })).toHaveAttribute("href", "/addons");
  });

  test("an edit of the add-on is confirmed and sent with the preview's digest", async ({ page }) => {
    await go(page, "/addons/platform/cert-manager");
    await page.getByRole("region", { name: "Add-on" }).getByRole("button", { name: "Edit add-on" }).click();
    const form = await editAddonForm(page);
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
    await page.getByRole("region", { name: "Add-on" }).getByRole("button", { name: "Edit add-on" }).click();
    await (await editAddonForm(page)).getByLabel("Contents of operators/cert-manager/values.yaml").fill("replicas: 2\n");
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
    await expect(replicas).toContainText("sig values");
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

});

test.describe("A hosted-cluster default, like an MCE one", () => {
  test.beforeEach(async ({ page }) => setUp(page));
  const hosted = (page: Page) => page.getByTestId("scope-hosted-clusters");

  test("has values per env and per cluster, and no deploying on specific clusters", async ({ page }) => {
    await go(page, "/addons/platform/external-secrets");
    await expect(hosted(page).getByTestId("env-prod")).toContainText("values-prod.yaml");
    await expect(hosted(page).getByTestId(`destination-${HOSTED_NAME}`)).toContainText(`values-${HOSTED_NAME}.yaml`);
    await expect(hosted(page).getByRole("button", { name: `Edit values override on ${HOSTED_NAME}` })).toBeEnabled();
    await expect(hosted(page).getByTestId("deploy-on-mces")).toHaveCount(0);
    await expect(hosted(page).getByTestId("hosted-clusters-note")).toContainText("no deploying it on specific hosted clusters here");
  });

  test("an env override shows the effective values before and after, and sends the env file", async ({ page }) => {
    await go(page, "/addons/platform/external-secrets");
    await hosted(page).getByRole("button", { name: "Edit values for prod" }).click();
    const form = formDialog(page);
    await expect(form.getByRole("heading", { name: "external-secrets values for prod" })).toBeVisible();
    await form.getByRole("button", { name: "YAML", exact: true }).click();
    await form.getByLabel("Contents of defaults/hosted-clusters/external-secrets/values-prod.yaml").fill("refreshInterval: 10m\n");
    const refresh = form.getByTestId("effective-refreshInterval");
    await expect(refresh).toContainText("5m");
    await expect(refresh).toContainText("10m");
    await expect(refresh).toContainText("fleet · env");
    // The preview edits the env file on a destination of that env.
    await expect
      .poll(() => requests.previews.some((p) => p.override_path === "defaults/hosted-clusters/external-secrets/values-prod.yaml"))
      .toBe(true);
    await form.getByRole("button", { name: "Preview changes" }).click();
    const plan = review(page);
    await expect(plan.getByTestId("authoring-plan")).toBeVisible();
    await plan.getByRole("checkbox", { name: /as listed/ }).first().click();
    await plan.getByRole("button", { name: /Create MR/ }).click();
    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("values for prod");
    const real = realWrites()[0];
    expect(real.method).toBe("PUT");
    expect(real.path).toBe("/api/day2/addons/platform/external-secrets/defaults/hosted-clusters/envs/prod/values");
    expect(real.body).toMatchObject({ values: { refreshInterval: "10m" }, expected_digest: expect.stringContaining("override-values") });
  });

  test("a hosted cluster's own values are written like an MCE's", async ({ page }) => {
    await go(page, "/addons/platform/external-secrets");
    await hosted(page).getByRole("button", { name: `Edit values override on ${HOSTED_NAME}` }).click();
    const form = formDialog(page);
    await expect(form.getByRole("heading", { name: `external-secrets values on ${HOSTED_NAME}` })).toBeVisible();
    await form.getByRole("radio", { name: /Delete it/ }).check();
    await form.getByRole("button", { name: "Preview changes" }).click();
    const plan = review(page);
    await plan.getByRole("checkbox", { name: /as listed/ }).first().click();
    await plan.getByRole("button", { name: /Create MR/ }).click();
    const real = realWrites()[0];
    expect(decodeURIComponent(real.path)).toBe(`/api/day2/addons/platform/external-secrets/defaults/hosted-clusters/destinations/${HOSTED_ID}/values`);
    expect(real.body).toMatchObject({ values: null });
  });
});

test.describe("Deploy on specific MCEs", () => {
  const panel = (page: Page) => page.getByTestId("deploy-on-mces");

  test("one install merge request per chosen MCE, previewed first", async ({ page }) => {
    await setUp(page);
    await go(page, "/addons/platform/external-secrets");
    await expect(panel(page).getByTestId(`installed-${MCE_EXCLUDED_NAME}`)).toContainText(
      `sites/site1/prod/mces/${MCE_EXCLUDED_NAME}/in-cluster/external-secrets`,
    );
    await expect(panel(page).getByRole("checkbox", { name: "Deploy on ocp4-prep-mce-site3-d" })).toBeDisabled();
    await expect(panel(page)).toContainText("Not registered with platform yet: installing registers it");
    await panel(page).getByRole("checkbox", { name: `Deploy on ${MCE_A_NAME}` }).click();
    await panel(page).getByRole("checkbox", { name: "Deploy on ocp4-prod-mce-site9-z" }).click();
    await panel(page).getByRole("button", { name: "Preview 2 installs" }).click();

    const plan = page.getByRole("dialog").filter({ has: page.getByTestId("mce-install-plan") });
    await expect(plan.getByTestId(`plan-${MCE_A_NAME}`)).toContainText("one merge request");
    await expect(plan.getByTestId(`plan-${MCE_A_NAME}`)).toContainText(`in-cluster/external-secrets/values.yaml`);
    await plan.getByRole("button", { name: "Open 2 merge requests" }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("2 merge requests opened");
    const writes = requests.writes.filter((w) => w.path.endsWith("/mce-installs"));
    expect(writes.map((w) => w.dryRun)).toEqual([true, false]);
    expect(writes[0].body).toEqual({ clusters: [MCE_A, MCE_UNREGISTERED], values: {}, message: null });
    expect(writes[1].body).toEqual(writes[0].body);
  });

  test("an MCE that fails fails alone, and the page says which", async ({ page }) => {
    await setUp(page, { failMce: MCE_A });
    await go(page, "/addons/platform/external-secrets");
    await panel(page).getByRole("checkbox", { name: `Deploy on ${MCE_A_NAME}` }).click();
    await panel(page).getByRole("checkbox", { name: "Deploy on ocp4-prod-mce-site9-z" }).click();
    await panel(page).getByRole("button", { name: "Preview 2 installs" }).click();
    await page.getByRole("button", { name: "Open 2 merge requests" }).click();
    const opened = page.getByRole("region", { name: "Opened merge requests" });
    await expect(opened).toContainText("Merge request opened");
    await expect(opened).toContainText(`${MCE_A_NAME}: GitLab refused the branch`);
  });

  test("an installed MCE is removed with the usual orphaning warning", async ({ page }) => {
    await setUp(page);
    await go(page, "/addons/platform/external-secrets");
    await panel(page).getByRole("button", { name: `Remove external-secrets from ${MCE_EXCLUDED_NAME}` }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("The workload keeps running.");
    const confirm = dialog.getByRole("button", { name: "Open removal MR" });
    await expect(confirm).toBeDisabled();
    await dialog.getByRole("textbox").fill("external-secrets");
    const removal = page.waitForRequest((r) => r.method() === "DELETE" && r.url().includes("/addons/platform/external-secrets"));
    await confirm.click();
    expect(decodeURIComponent((await removal).url())).toContain(`/api/day2/clusters/${MCE_EXCLUDED}/addons/platform/external-secrets`);
    await expect(page.getByRole("region", { name: "Opened merge requests" })).toBeVisible();
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
    await expect(page.getByRole("button", { name: "Edit add-on" })).toBeDisabled();
    await expect(page.getByTestId("scope-mces").getByRole("button", { name: "Edit the default on every MCE" })).toBeDisabled();
    await expect(page.getByTestId("scope-hub").getByRole("button", { name: "Make it a default" })).toBeDisabled();
    await expect(page.getByTestId("scope-mces").getByRole("button", { name: /values override/ }).first()).toBeDisabled();
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
    await expect(page.getByRole("button", { name: "Edit add-on" })).toBeDisabled();
  });

  test("writes stay off when the teams list fails", async ({ page }) => {
    await page.route("**/api/day2/teams", (r) => r.fulfill({ status: 503, body: "unavailable" }));
    await go(page, "/addons/platform/cert-manager");
    // The list is retried before it fails; until then and after, writes stay off.
    await expect(page.getByRole("button", { name: "Edit add-on" })).toBeDisabled();
    await expect(page.getByRole("note").first()).toContainText("Wingman could not read platform's write access yet.", { timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Edit add-on" })).toBeDisabled();
  });
});
