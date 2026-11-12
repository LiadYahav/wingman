/**
 * The day2 pages against the service's shapes (types/day2.ts): a destination's
 * charts, the values preview with provenance, install/update/remove/bulk, the
 * lints list, and the catalog. Every API call is mocked (e2e/fixtures/day2.ts).
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import {
  HOSTED_ID,
  HOSTED_NAME,
  MCE_ID,
  ORPHAN_NOTE,
  SYNC_NOTE,
  TWIN_IDS,
  UPI_ID,
  hostedCharts,
  mockDay2World,
  problem,
  type Day2Requests,
} from "../fixtures/day2";

let requests: Day2Requests;

test.beforeEach(async ({ page }) => {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  requests = await mockDay2World(page);
});

/** The legacy link from the day1 cluster page: a bare name and its MCE. */
const HOSTED_PAGE = `/clusters/${HOSTED_NAME}/addons?site=site1&mce=mce-a`;

const installedCard = (page: Page, team: string, name: string) => page.getByTestId(`installed-${team}-${name}`);
const availableCard = (page: Page, team: string, name: string) => page.getByTestId(`available-${team}-${name}`);

test.describe("A destination's charts", () => {
  test("lists its own charts and fleet defaults, and says Wingman cannot see ArgoCD", async ({ page }) => {
    await go(page, HOSTED_PAGE);

    await expect(page.getByRole("heading", { name: new RegExp(HOSTED_NAME) })).toBeVisible();
    await expect(page.getByText(HOSTED_ID)).toBeVisible();
    await expect(installedCard(page, "platform", "cert-manager")).toBeVisible();
    await expect(installedCard(page, "platform", "external-secrets")).toContainText("fleet default");
    await expect(installedCard(page, "observability", "prometheus")).toContainText("pinned");
    await expect(installedCard(page, "observability", "prometheus")).toContainText("2.44.0");
    await expect(page.getByText(/Wingman has no ArgoCD access yet/)).toBeVisible();
    // grafana is a fleet default excluded here, so it can be installed into the folder.
    await expect(page.getByText("observability/grafana")).toBeVisible();
    await expect(availableCard(page, "observability", "grafana")).toContainText("excluded fleet default");
  });

  test("the values preview says which layer set each value", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    const card = installedCard(page, "platform", "cert-manager");
    await card.getByRole("button", { name: /^cert-manager/ }).click();

    await expect(card.getByTestId("value-row-replicas")).toContainText("cluster");
    await expect(card.getByTestId("value-row-namespace")).toContainText("team");
    await expect(card.getByTestId("value-row-resources.limits.cpu")).toContainText("team");
    await expect(card.getByText(`sites/site1/prod/mces/mce-a/${HOSTED_NAME}/cert-manager/values.yaml`).first()).toBeVisible();

    await card.getByRole("tab", { name: "Layers" }).click();
    const layers = card.getByRole("list", { name: /Value layers/ });
    await expect(layers).toContainText("operators/cert-manager/values.yaml");
    await expect(layers).toContainText("no file");
    await expect(layers).toContainText("this edit");

    await card.getByRole("tab", { name: "Deployment" }).click();
    await expect(card).toContainText(`platform-${HOSTED_NAME}-cert-manager-deploy`);
    await expect(card).toContainText("manual: someone syncs it after merge");
  });

  test("an update sends last_commit_id and shows the MR with its notes", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    const card = installedCard(page, "platform", "cert-manager");
    await card.getByRole("button", { name: /^cert-manager/ }).click();

    await card.getByTestId("value-row-replicas").getByRole("textbox").fill("3");
    await card.getByRole("button", { name: "Review update" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("replicas: 3");
    await dialog.getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText(SYNC_NOTE);
    const write = requests.writes.find((w) => w.method === "PUT");
    // A number stays a number, and the edit is guarded by the commit it was read at (ADR-0006).
    expect(write?.body).toEqual({ override_values: { replicas: 3 }, last_commit_id: "c0ffee1" });
    expect(write?.url).toContain(`/clusters/${encodeURIComponent(HOSTED_ID)}/addons/platform/cert-manager`);
  });

  test("a stale update reloads the chart instead of overwriting the newer file", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    const charts = hostedCharts();
    const moved = {
      ...charts,
      installed: charts.installed.map((c) =>
        c.name === "cert-manager" ? { ...c, override_values: { replicas: 5 }, last_commit_id: "beef002" } : c,
      ),
    };
    await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons\/platform\/cert-manager(\?.*)?$/, async (route) => {
      if (route.request().method() !== "PUT") return route.fallback();
      // Someone else's change merged meanwhile: the listing now has the new commit.
      await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons(\?.*)?$/, (r) =>
        r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(moved) }),
      );
      return route.fulfill(problem(409, "REVISION_CONFLICT", "values.yaml changed since c0ffee1"));
    });

    const card = installedCard(page, "platform", "cert-manager");
    await card.getByRole("button", { name: /^cert-manager/ }).click();
    await card.getByTestId("value-row-replicas").getByRole("textbox").fill("3");
    await card.getByRole("button", { name: "Review update" }).click();
    await page.getByRole("dialog").getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByText(/changed since you opened it/)).toBeVisible();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(card.getByTestId("value-row-replicas").getByRole("textbox")).toHaveValue("5");
  });

  test("removing a chart says the workload keeps running", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    const card = installedCard(page, "platform", "cert-manager");
    await card.getByRole("button", { name: "Actions for cert-manager" }).click();
    await page.getByRole("button", { name: /Remove from this cluster/ }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("The workload keeps running.");
    await expect(dialog).toContainText(`argocd app delete platform-${HOSTED_NAME}-cert-manager-deploy --cascade`);
    const confirm = dialog.getByRole("button", { name: "Open removal MR" });
    await expect(confirm).toBeDisabled();
    await dialog.getByPlaceholder("cert-manager").fill("cert-manager");
    await confirm.click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText(ORPHAN_NOTE);
    const write = requests.writes.find((w) => w.method === "DELETE");
    expect(new URL(write!.url).searchParams.get("last_commit_id")).toBe("c0ffee1");
  });

  test("a fleet default points at its add-on page instead of a remove", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    await installedCard(page, "platform", "external-secrets").getByRole("button", { name: "Actions for external-secrets" }).click();
    const note = page.getByText("A fleet default is not removed per cluster");
    await expect(note).toBeVisible();
    await expect(note).not.toContainText(/untick|exclusions/);
    await expect(page.getByRole("link", { name: "its add-on page" })).toHaveAttribute("href", "/addons/platform/external-secrets");
    await expect(page.getByRole("button", { name: /Remove from/ })).toHaveCount(0);
  });

  test("an install writes only the values set, with no version pin", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    const card = availableCard(page, "observability", "grafana");
    await card.getByRole("button", { name: "Install" }).click();
    await card.getByTestId("value-row-persistence.size").getByRole("textbox").fill("20Gi");
    await card.getByRole("button", { name: "Review install" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(`sites/site1/prod/mces/mce-a/${HOSTED_NAME}/grafana/values.yaml`);
    await dialog.getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toBeVisible();
    expect(requests.writes.find((w) => w.method === "POST")?.body).toEqual({
      override_values: { persistence: { size: "20Gi" } },
    });
  });

  test("a chart offered both ways (XOR) shows the service's refusal", async ({ page }) => {
    await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons\/observability\/grafana(\?.*)?$/, (route) =>
      route.request().method() === "POST"
        ? route.fulfill(
            problem(409, "ALREADY_EXISTS", "grafana is a fleet default of observability; a chart folder for it would generate the same app twice (the XOR rule)", { rule: "xor" }),
          )
        : route.fallback(),
    );
    await go(page, HOSTED_PAGE);
    const card = availableCard(page, "observability", "grafana");
    await card.getByRole("button", { name: "Install" }).click();
    await card.getByRole("button", { name: "Review install" }).click();
    await page.getByRole("dialog").getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByRole("dialog").getByRole("alert")).toContainText("the XOR rule");
  });

  test("a chart with only the miscased repoUrl needs a repourl to install", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    const card = availableCard(page, "security", "kyverno");
    await card.getByRole("button", { name: "Install" }).click();
    await expect(card).toContainText("repourl-miscased");
    const review = card.getByRole("button", { name: "Review install" });
    await expect(review).toBeDisabled();

    await card.getByPlaceholder(/helm-charts/).fill("https://gitlab.example.com/helm-charts/kyverno.git");
    await review.click();
    await page.getByRole("dialog").getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toBeVisible();
    expect(requests.writes.find((w) => w.method === "POST")?.body).toEqual({
      override_values: {},
      repourl: "https://gitlab.example.com/helm-charts/kyverno.git",
    });
  });

  test("choosing another revision is an emergency pin that must be confirmed", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    const card = installedCard(page, "platform", "cert-manager");
    await card.getByRole("button", { name: /^cert-manager/ }).click();
    await card.getByRole("combobox", { name: "Revision" }).click();
    await page.getByRole("option", { name: "1.11.0", exact: true }).click();

    await expect(card).toContainText("emergency pin");
    const review = card.getByRole("button", { name: "Review update" });
    await expect(review).toBeDisabled();
    await card.getByRole("checkbox").click();
    await review.click();
    await page.getByRole("dialog").getByRole("button", { name: /Create MR/ }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toBeVisible();
    expect(requests.writes.find((w) => w.method === "PUT")?.body).toMatchObject({
      version: "1.11.0",
      emergency_pin: true,
      last_commit_id: "c0ffee1",
    });
  });

  test("a bulk install opens one MR per team", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    await availableCard(page, "observability", "grafana").getByRole("checkbox").click();
    await availableCard(page, "networking", "ingress-nginx").getByRole("checkbox").click();
    await page.getByRole("button", { name: "Install selected" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("2 merge requests, one per team");
    await dialog.getByRole("button", { name: "Open 2 MRs" }).click();

    await expect(page.getByRole("region", { name: "Opened merge requests" })).toContainText("2 merge requests opened");
    const body = requests.writes.find((w) => w.url.endsWith("/addons/bulk"))?.body as { addons: { team: string; addon: string }[] };
    expect(body.addons.map((a) => `${a.team}/${a.addon}`).sort()).toEqual(["networking/ingress-nginx", "observability/grafana"]);
    await expect(page.getByRole("button", { name: "Install selected" })).toBeHidden();
  });

  test("the upgrade check lists charts that would lose their OCP pin", async ({ page }) => {
    await go(page, HOSTED_PAGE);
    await page.getByLabel("Upgrade check", { exact: true }).fill("4.19.3");
    await page.getByRole("button", { name: "Check", exact: true }).click();
    await expect(page.getByText(/no ocp-versions\/4\.19\.3\//)).toBeVisible();
  });

  test("a name two destinations share asks which one", async ({ page }) => {
    await go(page, "/clusters/twin/addons");
    await expect(page.getByText("twin names 2 destinations")).toBeVisible();
    await page.getByRole("link", { name: TWIN_IDS[1] }).click();
    await expect(page).toHaveURL(new RegExp(`/clusters/${encodeURIComponent(TWIN_IDS[1])}/addons`));
  });

  test("the back link goes to a hosted cluster's page, and from any other kind to the add-ons", async ({ page }) => {
    const back = page.getByRole("link", { name: "Back", exact: true });
    await go(page, HOSTED_PAGE);
    await expect(installedCard(page, "platform", "cert-manager")).toBeVisible();
    await expect(back).toHaveAttribute("href", `/clusters/${HOSTED_NAME}?site=site1&mce=mce-a`);
    for (const id of ["hub", MCE_ID, UPI_ID]) {
      await go(page, `/clusters/${encodeURIComponent(id)}/addons`);
      await expect(page.getByTestId("installed-empty")).toBeVisible();
      await expect(back).toHaveAttribute("href", "/addons");
    }
  });

  test("the hub is a destination too, without an OCP version", async ({ page }) => {
    await go(page, "/clusters/hub/addons");
    await expect(page.getByRole("heading", { name: /hub/ })).toBeVisible();
    await expect(page.getByText("Hub", { exact: true })).toBeVisible();
    await expect(page.getByText(/No team deploys a chart to hub yet/)).toBeVisible();
    await expect(page.getByLabel("Upgrade check", { exact: true })).toHaveCount(0);
  });
});

test.describe("Destinations", () => {
  test("the removed Destinations page's link opens the clusters, and the sidebar has no entry", async ({ page }) => {
    await go(page, "/destinations");
    await expect(page).toHaveURL(/\/clusters$/);
    await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Destinations" })).toHaveCount(0);
  });
});

test.describe("Lints", () => {
  test("lists findings worst first and filters by severity", async ({ page }) => {
    await go(page, "/lints");
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(3);
    await expect(rows.first()).toContainText("repourl-missing");
    await page.getByRole("group", { name: "Severity" }).getByRole("button", { name: /error/ }).click();
    await expect(rows).toHaveCount(1);
    await expect(rows.first().getByRole("link", { name: MCE_ID })).toBeVisible();
  });
});

test.describe("Catalog", () => {
  test("shows fleet-default scopes, OCP pins and the miscased repoUrl", async ({ page }) => {
    await go(page, "/addons");
    await expect(page.getByText("6 charts across 4 teams · 1 with warnings")).toBeVisible();
    await expect(page.getByText("No lowercase repourl")).toBeVisible();
    await page.getByRole("button", { name: /prometheus/ }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("tab", { name: "Versions" }).click();
    await expect(dialog).toContainText("4.18.22");
    await expect(dialog).toContainText("2.44.0");
  });
});
