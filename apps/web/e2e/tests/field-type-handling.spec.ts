import { test, expect } from "@playwright/test";
import { SpecNewPage } from "../pages/spec-new.page";
import { ConfigureDialogPage } from "../pages/configure-dialog.page";
import { mockAllApis } from "../fixtures/api-handlers";

test.describe("Field Type Handling", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("correctly detects array type for arrays", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "external-secrets");
    await specPage.openConfigureDialog("platform", "external-secrets");

    await configDialog.waitForOpen();

    const secretStoresRow = configDialog.getFieldRow("secretStores");
    await expect(secretStoresRow.getByText("array")).toBeVisible();
  });

  test("correctly detects object type for nested objects", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();

    const resourcesRow = configDialog.getFieldRow("resources.requests");
    await expect(resourcesRow.getByText("object")).toBeVisible();
  });

  test("shows correct value summary for arrays", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("observability", "grafana");
    await specPage.openConfigureDialog("observability", "grafana");

    await configDialog.waitForOpen();

    const dashboardsRow = configDialog.getFieldRow("dashboards");
    await expect(dashboardsRow.getByText(/empty array/i)).toBeVisible();
  });

  test("shows correct value summary for objects", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("observability", "grafana");
    await specPage.openConfigureDialog("observability", "grafana");

    await configDialog.waitForOpen();

    const persistenceRow = configDialog.getFieldRow("persistence");
    await expect(persistenceRow.getByText(/2 propert/i)).toBeVisible();
  });

  test("shows correct value summary for booleans", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();

    const installCRDsRow = configDialog.getFieldRow("installCRDs");
    await expect(installCRDsRow.getByText("true")).toBeVisible();
  });

  test("shows correct value summary for integers", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();

    const replicasRow = configDialog.getFieldRow("replicas");
    await expect(replicasRow.getByText("1")).toBeVisible();
  });

  test("shows correct value summary for strings", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();

    const namespaceRow = configDialog.getFieldRow("namespace");
    await expect(namespaceRow.getByText('"cert-manager"')).toBeVisible();
  });

  test("type badge has correct color for each type", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();

    const integerBadge = configDialog.getFieldRow("replicas").locator("span:has-text('integer')");
    await expect(integerBadge).toHaveClass(/text-amber/);

    const stringBadge = configDialog.getFieldRow("namespace").locator("span:has-text('string')");
    await expect(stringBadge).toHaveClass(/text-blue/);

    const booleanBadge = configDialog
      .getFieldRow("installCRDs")
      .locator("span:has-text('boolean')");
    await expect(booleanBadge).toHaveClass(/text-green/);
  });
});
