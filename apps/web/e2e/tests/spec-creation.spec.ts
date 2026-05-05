import { test, expect } from "@playwright/test";
import { SpecNewPage } from "../pages/spec-new.page";
import { mockAllApis } from "../fixtures/api-handlers";

test.describe("Spec Creation", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("can create a new spec with basic info", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.fillBasicInfo("test-spec", "Test Spec", "A test spec for e2e");

    await expect(specPage.nameInput).toHaveValue("test-spec");
    await expect(specPage.displayNameInput).toHaveValue("Test Spec");
  });

  test("shows addon catalog with teams", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await expect(page.getByText("platform")).toBeVisible();
    await expect(page.getByText("observability")).toBeVisible();
    await expect(page.getByText("networking")).toBeVisible();
  });

  test("can search addons", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.searchAddons("cert");
    await expect(specPage.getAddonCard("platform", "cert-manager")).toBeVisible();
    await expect(specPage.getAddonCard("observability", "prometheus")).not.toBeVisible();
  });

  test("can add addon to spec", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.selectAddon("platform", "cert-manager");

    await expect(specPage.getSelectedAddon("platform", "cert-manager")).toBeVisible();
  });

  test("can remove addon from spec", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.selectAddon("platform", "cert-manager");
    await expect(specPage.getSelectedAddon("platform", "cert-manager")).toBeVisible();

    const selectedAddon = specPage.getSelectedAddon("platform", "cert-manager");
    await selectedAddon.getByRole("button", { name: /remove/i }).click();

    await expect(specPage.getSelectedAddon("platform", "cert-manager")).not.toBeVisible();
  });

  test("shows empty state when no addons selected", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await expect(page.getByText(/no addons selected/i)).toBeVisible();
  });
});
