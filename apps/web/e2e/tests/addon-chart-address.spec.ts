/**
 * A new add-on's chart address (ADR-0060), mocked: a team's charts sit in
 * `<team>/helm-charts` on Wingman's GitLab, so the New add-on form fills the
 * address in as the add-on template's `repourl_prefix` plus `<name>.git`
 * while the name is typed, until the person edits it; their address is kept
 * and sent. Each team gets its own group. An install that must give a
 * `repourl` shows the team's address as its placeholder.
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { HOSTED_NAME, mockDay2World } from "../fixtures/day2";
import { mockAuthoring } from "../fixtures/authoring";
import { mockAddonDetail, type AddonRequests } from "../fixtures/addon-detail";

const PLATFORM = "https://gitlab.example.com/platform/helm-charts/";

test.beforeEach(async ({ page }) => {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
});

async function newAddonForm(page: Page, team: string) {
  await go(page, `/addons/new?team=${team}`);
  const form = page.getByTestId("new-addon-form");
  await expect(form).toBeVisible();
  return {
    form,
    name: form.getByRole("textbox", { name: /^Name/ }),
    address: form.getByRole("textbox", { name: /Chart repo URL/ }),
  };
}

test.describe("A new add-on's chart address", () => {
  let requests: AddonRequests;

  test.beforeEach(async ({ page }) => {
    await mockDay2World(page);
    await mockAuthoring(page);
    requests = await mockAddonDetail(page);
  });

  test("follows the name in the team's charts group, and says why", async ({ page }) => {
    const { form, name, address } = await newAddonForm(page, "platform");
    await expect(address).toHaveValue("");
    await expect(address).toHaveAttribute("placeholder", `${PLATFORM}<name>.git`);

    await name.pressSequentially("pod");
    await expect(address).toHaveValue(`${PLATFORM}pod.git`);
    await name.pressSequentially("info");
    await expect(address).toHaveValue(`${PLATFORM}podinfo.git`);

    await form.getByRole("button", { name: "About Chart repo URL (repourl)" }).hover();
    const tooltip = page.locator("[data-slot=tooltip-content][data-open]");
    await expect(tooltip).toContainText("A team's charts sit in <team>/helm-charts on Wingman's GitLab, here platform/helm-charts");
    await expect(tooltip).toContainText("It can be changed to any chart repo.");
  });

  test("keeps an address the person edited, and sends it", async ({ page }) => {
    const { form, name, address } = await newAddonForm(page, "platform");
    await name.fill("podinfo");
    await address.fill("https://charts.example.org/podinfo.git");
    await name.fill("podinfo-two");
    await expect(address).toHaveValue("https://charts.example.org/podinfo.git");

    await form.getByRole("button", { name: "Preview changes" }).click();
    await expect(page.getByRole("dialog").getByTestId("authoring-plan")).toBeVisible();
    const [preview] = requests.writes.filter((w) => w.dryRun);
    expect(preview.body).toMatchObject({ name: "podinfo-two", repourl: "https://charts.example.org/podinfo.git" });
  });

  test("uses each team's own group", async ({ page }) => {
    const { name, address } = await newAddonForm(page, "networking");
    await expect(address).toHaveAttribute("placeholder", "https://gitlab.example.com/networking/helm-charts/<name>.git");
    await name.fill("external-dns");
    await expect(address).toHaveValue("https://gitlab.example.com/networking/helm-charts/external-dns.git");
  });
});

test("an install that must give a repourl suggests the team's address", async ({ page }) => {
  await mockDay2World(page);
  await go(page, `/clusters/${HOSTED_NAME}/addons?site=site1&mce=mce-a`);
  const card = page.getByTestId("available-security-kyverno");
  await card.getByRole("button", { name: "Install" }).click();
  await expect(card.getByRole("textbox", { name: /Chart repo URL/ })).toHaveAttribute("placeholder", "https://gitlab.example.com/security/helm-charts/kyverno.git");
});
