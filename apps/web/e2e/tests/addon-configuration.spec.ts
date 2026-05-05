import { test, expect } from "@playwright/test";
import { SpecNewPage } from "../pages/spec-new.page";
import { ConfigureDialogPage } from "../pages/configure-dialog.page";
import { mockAllApis } from "../fixtures/api-handlers";

test.describe("Addon Configuration", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("can open configure dialog for addon", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();
    await expect(configDialog.dialog).toBeVisible();
    await expect(page.getByText("Configure Overrideable Fields")).toBeVisible();
  });

  test("shows available fields from addon default values", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();

    await expect(configDialog.getFieldRow("replicas")).toBeVisible();
    await expect(configDialog.getFieldRow("namespace")).toBeVisible();
    await expect(configDialog.getFieldRow("installCRDs")).toBeVisible();
  });

  test("can select field to make overrideable", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();
    await configDialog.toggleField("replicas");

    await expect(configDialog.getFieldCheckbox("replicas")).toBeChecked();
    expect(await configDialog.getSelectedFieldCount()).toBe(1);
  });

  test("shows expanded options when field selected", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();
    await configDialog.toggleField("replicas");

    await expect(configDialog.getFieldTypeSelect("replicas")).toBeVisible();
    await expect(configDialog.getFieldHelpInput("replicas")).toBeVisible();
  });

  test("can set help text for field", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();
    await configDialog.toggleField("replicas");
    await configDialog.setFieldHelp("replicas", "Number of cert-manager pods to run");

    await expect(configDialog.getFieldHelpInput("replicas")).toHaveValue(
      "Number of cert-manager pods to run"
    );
  });

  test("correctly detects integer type", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();

    const replicasRow = configDialog.getFieldRow("replicas");
    await expect(replicasRow.getByText("integer")).toBeVisible();
  });

  test("correctly detects boolean type", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();

    const installCRDsRow = configDialog.getFieldRow("installCRDs");
    await expect(installCRDsRow.getByText("boolean")).toBeVisible();
  });

  test("shows no fields message for empty addon", async ({ page }) => {
    await page.route("**/api/day2/addons/empty/test", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          team: "empty",
          name: "test",
          description: "Empty addon",
          version: "1.0.0",
          defaultValues: {},
        }),
      });
    });

    await page.route("**/api/day2/addons", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            team: "empty",
            name: "test",
            description: "Empty addon",
            version: "1.0.0",
            defaultValues: {},
          },
        ]),
      });
    });

    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("empty", "test");
    await specPage.openConfigureDialog("empty", "test");

    await configDialog.waitForOpen();
    await expect(configDialog.noFieldsMessage).toBeVisible();
  });

  test("can save configuration", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();
    await configDialog.configureField("replicas", {
      help: "Number of replicas",
    });

    await configDialog.save();
    await expect(configDialog.dialog).not.toBeVisible();
  });

  test("can cancel configuration", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();
    await configDialog.toggleField("replicas");
    await configDialog.cancel();

    await expect(configDialog.dialog).not.toBeVisible();
  });

  test("preserves configured fields count on selected addon", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    const configDialog = new ConfigureDialogPage(page);

    await specPage.goto();
    await specPage.selectAddon("platform", "cert-manager");
    await specPage.openConfigureDialog("platform", "cert-manager");

    await configDialog.waitForOpen();
    await configDialog.toggleField("replicas");
    await configDialog.toggleField("namespace");
    await configDialog.save();

    const selectedAddon = specPage.getSelectedAddon("platform", "cert-manager");
    await expect(selectedAddon.getByText(/2 field/i)).toBeVisible();
  });
});
