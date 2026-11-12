/**
 * Add-on authoring and per-team write access (ADR-0043), mocked: a new
 * add-on from the team's template, making an add-on a fleet default (the
 * clusters that move into it, each changed one confirmed), editing a team
 * default and a fleet default, and a team that has not given Wingman write
 * access. Every write is previewed with `?dry_run=true` first, and what was
 * previewed is what is sent (docs/notes/2026-11-12-day2-addon-authoring-api.md).
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { HOSTED_ID, HOSTED_NAME, mockDay2World, problem } from "../fixtures/day2";
import { AUTHORING_NOTE, MANUAL, READ_ONLY_REASON, TEAMS, mockAuthoring, type AuthoringRequests } from "../fixtures/authoring";

let requests: AuthoringRequests;

test.beforeEach(async ({ page }) => {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await mockDay2World(page);
  requests = await mockAuthoring(page);
});

const teamSection = (page: Page, team: string) => page.getByTestId(`team-${team}`);
const realWrites = () => requests.writes.filter((w) => !w.dryRun);
const dryRuns = () => requests.writes.filter((w) => w.dryRun);

/** The authoring form: the dialog with Preview (another may still be closing). */
const formDialog = (page: Page) => page.getByRole("dialog").filter({ has: page.getByRole("button", { name: "Preview changes" }) });

/** Preview (the dry run): the review dialog with the plan. */
async function preview(page: Page) {
  await formDialog(page).getByRole("button", { name: "Preview changes" }).click();
  const review = page.getByRole("dialog").filter({ has: page.getByTestId("authoring-plan") });
  await expect(review.getByTestId("authoring-plan")).toBeVisible();
  return review;
}

test.describe("A new add-on", () => {
  test("starts from the team's files, keeps the sync rules, and sends what was previewed", async ({ page }) => {
    await go(page, "/addons");
    await teamSection(page, "platform").getByRole("button", { name: "New add-on" }).click();
    const form = formDialog(page);
    await expect(form.getByRole("heading", { name: "New add-on in platform" })).toBeVisible();

    await form.getByRole("textbox", { name: /^Name/ }).fill("podinfo");
    // Pre-filled from the template while untouched: the team's chart-repo folder and the name as namespace.
    await expect(form.getByRole("textbox", { name: /Chart repo URL/ })).toHaveValue("https://gitlab.example.com/helm-charts/podinfo.git");
    await expect(form.getByRole("textbox", { name: /Project namespace/ })).toHaveValue("podinfo");
    await expect(form.getByText("Pre-filled from the sync options most of sigs/platform's add-ons use (2 of 2).")).toBeVisible();

    // Manual sync by default: prune and self-heal exist only with auto-sync.
    const auto = form.getByRole("switch", { name: "Auto-sync" });
    const prune = form.getByRole("checkbox", { name: /^Prune\b/ });
    const selfHeal = form.getByRole("checkbox", { name: /^Self-heal/ });
    await expect(auto).not.toBeChecked();
    await expect(form.getByTestId("sync-mode-note")).toContainText("nothing deploys after the merge until someone syncs");
    await expect(prune).toBeDisabled();
    await expect(form.getByRole("checkbox", { name: "CreateNamespace=true" })).toBeChecked();

    await auto.click();
    await expect(prune).toBeEnabled();
    await prune.click();
    await expect(prune).toBeChecked();
    await auto.click();
    // Turning auto-sync off clears them.
    await expect(prune).not.toBeChecked();
    await expect(prune).toBeDisabled();
    await auto.click();
    await selfHeal.click();

    const other = form.getByRole("textbox", { name: "Another sync option" });
    await other.fill("not an option");
    await form.getByRole("button", { name: "Add", exact: true }).click();
    await expect(form.getByText("An option is Name=value")).toBeVisible();
    await other.fill("CreateNamespace=true");
    await form.getByRole("button", { name: "Add", exact: true }).click();
    await expect(form.getByText("CreateNamespace=true is already on the list.")).toBeVisible();
    await other.fill("ServerSideApply=true");
    await form.getByRole("button", { name: "Add", exact: true }).click();
    await expect(form.getByRole("checkbox", { name: "ServerSideApply=true" })).toBeChecked();
    await other.fill("SkipHooks=true");
    await other.press("Enter");
    await expect(form.getByRole("list", { name: "Other sync options" })).toContainText("SkipHooks=true");

    await form.getByLabel("Contents of operators/podinfo/values.yaml").fill("replicaCount: 2\n");
    await form.getByRole("radio", { name: /every hosted cluster/ }).check();
    await expect(form.getByText("3 destinations today")).toBeVisible();

    const review = await preview(page);
    await expect(review).toContainText("operators/podinfo/podinfo.yaml");
    await expect(review).toContainText("defaults/hosted-clusters/podinfo/values.yaml");
    await expect(review).toContainText("Reaches 3 destinations");
    await expect(review).toContainText(AUTHORING_NOTE);
    expect(dryRuns()).toHaveLength(1);
    expect(new URL(dryRuns()[0].url).pathname).toBe("/api/day2/addons/platform");
    expect(realWrites()).toHaveLength(0);

    await review.getByRole("button", { name: /Create MR/ }).click();
    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText(
      "[Wingman/Day2] Create addon platform/podinfo in the team catalog",
    );
    const expected = {
      name: "podinfo",
      repourl: "https://gitlab.example.com/helm-charts/podinfo.git",
      target_revision: null,
      path: null,
      project_namespace: "podinfo",
      sync: { auto_sync: true, prune: false, self_heal: true, sync_options: ["CreateNamespace=true", "ServerSideApply=true", "SkipHooks=true"] },
      ignore_differences: null,
      values: { replicaCount: 2 },
      default_scope: "hosted-clusters",
      default_values: {},
      confirm_changes: [],
      message: null,
    };
    expect(dryRuns()[0].body).toEqual(expected);
    expect(realWrites()).toHaveLength(1);
    expect(realWrites()[0].body).toEqual(expected);
    expect(realWrites()[0].method).toBe("POST");
  });

  test("a name that is taken or not a DNS label cannot be previewed", async ({ page }) => {
    await go(page, "/addons");
    await teamSection(page, "platform").getByRole("button", { name: "New add-on" }).click();
    const form = formDialog(page);
    const button = form.getByRole("button", { name: "Preview changes" });
    const name = form.getByRole("textbox", { name: /^Name/ });
    await name.fill("cert-manager");
    await expect(button).toBeDisabled();
    await expect(button).toHaveAttribute("title", "platform has cert-manager in its catalog already");
    await name.fill("Pod_Info");
    await expect(button).toHaveAttribute("title", /lowercase letters, digits and '-'/);
    await name.fill("podinfo");
    await expect(button).toBeEnabled();
  });
});

test.describe("Make default", () => {
  test("lists the clusters that move into the default, and each changed one must be confirmed", async ({ page }) => {
    await go(page, "/addons");
    await page.getByRole("button", { name: /^cert-manager/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Make default" }).click();
    const form = formDialog(page);
    await expect(form.getByRole("heading", { name: "Make platform/cert-manager a fleet default" })).toBeVisible();
    await form.getByRole("radio", { name: /every hosted cluster/ }).check();
    await expect(form.getByRole("radio", { name: /Inherit the team default's/ })).toBeChecked();

    const review = await preview(page);
    await expect(review).toContainText("2 clusters have cert-manager in their own folder.");
    const changed = review.getByTestId(`adopted-${HOSTED_NAME}`);
    await expect(changed).toContainText(`defaults/hosted-clusters/cert-manager/values-${HOSTED_NAME}.yaml`);
    await expect(changed).toContainText("projectNamespace");
    await expect(changed).toContainText("certs");
    await expect(review.getByTestId("adopted-twin")).toContainText("Unchanged");
    await expect(review.getByTestId("adopted-twin")).toContainText("sites/site1/prod/mces/mce-a/twin/.gitkeep");

    const confirm = review.getByRole("button", { name: /Create MR/ });
    await expect(confirm).toBeDisabled();
    await changed.getByRole("checkbox", { name: `I understand ${HOSTED_NAME} changes as listed` }).click();
    await expect(confirm).toBeEnabled();
    await confirm.click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("Promote addon platform/cert-manager");
    expect(dryRuns()[0].body).toEqual({ values: {}, sync: null, confirm_changes: [], message: null });
    const real = realWrites()[0];
    expect(new URL(real.url).pathname).toBe("/api/day2/addons/platform/cert-manager/defaults/hosted-clusters");
    expect(real.body).toEqual({ values: {}, sync: null, confirm_changes: [HOSTED_ID], message: null });
  });

  test("a scope where it is a default already cannot be chosen", async ({ page }) => {
    await go(page, "/addons");
    await page.getByRole("button", { name: /^external-secrets/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Make default" }).click();
    const form = formDialog(page);
    await expect(form.getByRole("radio", { name: /every hosted cluster/ })).toBeDisabled();
    await expect(form.getByText("a fleet default there already")).toBeVisible();
    await expect(form.getByRole("radio", { name: /every MCE/ })).toBeEnabled();
  });
});

test.describe("Team default", () => {
  test("an edit sends only what changed, with the commit the entry was read at", async ({ page }) => {
    await go(page, "/addons");
    await page.getByRole("button", { name: /^prometheus/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Edit team default" }).click();
    const form = formDialog(page);
    await expect(form.getByRole("heading", { name: "Edit the team default of observability/prometheus" })).toBeVisible();
    const button = form.getByRole("button", { name: "Preview changes" });
    await expect(button).toBeDisabled();
    await expect(button).toHaveAttribute("title", "No changes yet");

    await form.getByRole("switch", { name: "Auto-sync" }).click();
    await form.getByRole("checkbox", { name: /^Self-heal/ }).click();
    const review = await preview(page);
    await expect(review).toContainText("operators/prometheus/prometheus.yaml");
    await review.getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("team default");
    const real = realWrites()[0];
    expect(real.method).toBe("PUT");
    expect(new URL(real.url).pathname).toBe("/api/day2/addons/observability/prometheus");
    expect(real.body).toEqual({
      last_commit_id: "observability-catalog-1",
      sync: { ...MANUAL, auto_sync: true, self_heal: true },
    });
  });

  test("a blank revision removes the key (HEAD)", async ({ page }) => {
    await go(page, "/addons");
    await page.getByRole("button", { name: /^prometheus/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Edit team default" }).click();
    const form = formDialog(page);
    await form.getByRole("combobox", { name: /Revision/ }).fill("");
    await preview(page);
    expect(dryRuns()[0].body).toEqual({ last_commit_id: "observability-catalog-1", target_revision: null });
  });
});

test.describe("Fleet defaults", () => {
  test("are listed per team, and an edit can go back to the team default's sync options", async ({ page }) => {
    await go(page, "/addons");
    const row = page.getByTestId("fleet-default-platform-external-secrets-hosted-clusters");
    await expect(row).toContainText("every hosted cluster");
    await expect(row).toContainText("reaches 3 destinations");
    await expect(row).toContainText("auto-sync (self-heal)");
    await expect(row).toContainText("set by the fleet default");
    await expect(page.getByTestId("fleet-default-observability-grafana-hosted-clusters")).toContainText("1 excluded");
    await expect(teamSection(page, "platform").getByTestId("no-stop-default-note")).toContainText("orphans the workloads");

    await row.getByRole("button", { name: "Edit fleet default" }).click();
    const form = formDialog(page);
    await expect(form.getByRole("radio", { name: /Set them for this fleet default/ })).toBeChecked();
    await form.getByRole("radio", { name: /Inherit the team default's/ }).check();
    const review = await preview(page);
    await review.getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toBeVisible();
    const real = realWrites()[0];
    expect(real.method).toBe("PUT");
    expect(new URL(real.url).pathname).toBe("/api/day2/addons/platform/external-secrets/defaults/hosted-clusters");
    expect(real.body).toEqual({ last_commit_id: "platform-fleet-1", sync: null });
  });
});

test.describe("A read-only team", () => {
  test("says why next to every write it does not offer", async ({ page }) => {
    await go(page, "/addons");
    const security = teamSection(page, "security");
    await expect(security).toContainText("read-only");
    await expect(security.getByRole("note")).toContainText(READ_ONLY_REASON);
    await expect(security.getByRole("button", { name: "New add-on" })).toBeDisabled();
    await expect(security.getByTestId("fleet-default-security-kyverno-mces").getByRole("button", { name: "Edit fleet default" })).toBeDisabled();
    // A writable team offers them.
    await expect(teamSection(page, "platform").getByRole("button", { name: "New add-on" })).toBeEnabled();

    await security.getByRole("button", { name: /^kyverno/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("note")).toContainText(READ_ONLY_REASON);
    await expect(dialog.getByRole("button", { name: "Make default" })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Edit team default" })).toBeDisabled();
  });

  test("its charts on a cluster cannot be installed, and the page says why", async ({ page }) => {
    await go(page, `/clusters/${HOSTED_NAME}/addons?site=site1&mce=mce-a`);
    const available = page.getByRole("region", { name: "Available" });
    const kyverno = page.getByTestId("available-security-kyverno");
    await expect(kyverno.getByRole("button", { name: "Install" })).toBeDisabled();
    await expect(available.getByRole("note")).toContainText(READ_ONLY_REASON);
    await expect(page.getByTestId("available-observability-grafana").getByRole("button", { name: "Install" })).toBeEnabled();
  });

  test("a refusal from the service shows its detail", async ({ page }) => {
    // The list says writable; the service knows better (the access changed since).
    await mockAuthoring(page, { teams: TEAMS.map((t) => ({ ...t, writable: true, read_only_reason: null })) });
    await page.route(/\/api\/day2\/addons\/[^/?]+(\?.*)?$/, (r) =>
      r.request().method() === "GET"
        ? r.fallback()
        : r.fulfill(problem(403, "TEAM_READ_ONLY", READ_ONLY_REASON, { team: "security", access_level: 20, required_level: 30 })),
    );
    await go(page, "/addons");
    await teamSection(page, "security").getByRole("button", { name: "New add-on" }).click();
    const form = formDialog(page);
    await form.getByRole("textbox", { name: /^Name/ }).fill("falco");
    await form.getByRole("button", { name: "Preview changes" }).click();
    const alert = form.getByRole("alert");
    await expect(alert).toContainText("This team is read-only in Wingman");
    await expect(alert).toContainText(READ_ONLY_REASON);
  });
});
