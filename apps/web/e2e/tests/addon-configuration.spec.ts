import { test, expect } from "@playwright/test";
import { openConfigureDialog } from "../pages/configure-dialog.page";
import { mockAllApis } from "../fixtures/api-handlers";
import { catalogEntry } from "../fixtures/addons";

test.describe("Addon Configuration", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("can open configure dialog for addon", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");
    await expect(configDialog.dialog).toBeVisible();
    await expect(page.getByText("Configure Overrideable Fields")).toBeVisible();
  });

  test("shows available fields from addon default values", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");

    await expect(configDialog.getFieldRow("replicas")).toBeVisible();
    await expect(configDialog.getFieldRow("namespace")).toBeVisible();
    await expect(configDialog.getFieldRow("installCRDs")).toBeVisible();
  });

  test("can select field to make overrideable", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");
    await configDialog.toggleField("replicas");

    await expect(configDialog.getFieldCheckbox("replicas")).toBeChecked();
    expect(await configDialog.getSelectedFieldCount()).toBe(1);
  });

  test("shows expanded options when field selected", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");
    await configDialog.toggleField("replicas");

    await expect(configDialog.getFieldTypeSelect("replicas")).toBeVisible();
    await expect(configDialog.getFieldHelpInput("replicas")).toBeVisible();
  });

  test("can set help text for field", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");
    await configDialog.toggleField("replicas");
    await configDialog.setFieldHelp("replicas", "Number of cert-manager pods to run");

    await expect(configDialog.getFieldHelpInput("replicas")).toHaveValue(
      "Number of cert-manager pods to run"
    );
  });

  test("correctly detects integer type", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");

    const replicasRow = configDialog.getFieldRow("replicas");
    await expect(replicasRow.getByText("integer")).toBeVisible();
  });

  test("correctly detects boolean type", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");

    const installCRDsRow = configDialog.getFieldRow("installCRDs");
    await expect(installCRDsRow.getByText("boolean")).toBeVisible();
  });

  test("shows no fields message for empty addon", async ({ page }) => {
    // Chart values for empty/test fall through to mockDay2Api's empty "{}" response
    await page.route("**/api/day2/addons", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          catalogEntry({
            team: "empty",
            name: "test",
            current_version: "1.0.0",
            available_versions: ["1.0.0"],
            default_values: {},
          }),
        ]),
      });
    });

    const { configDialog } = await openConfigureDialog(page, "empty", "test");
    await expect(configDialog.noFieldsMessage).toBeVisible();
  });

  test("can save configuration", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");
    await configDialog.configureField("replicas", {
      help: "Number of replicas",
    });

    await configDialog.save();
    await expect(configDialog.dialog).not.toBeVisible();
  });

  test("can cancel configuration", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");
    await configDialog.toggleField("replicas");
    await configDialog.cancel();

    await expect(configDialog.dialog).not.toBeVisible();
  });

  test("preserves configured fields count on selected addon", async ({ page }) => {
    const { specPage, configDialog } = await openConfigureDialog(page, "platform", "cert-manager");
    await configDialog.toggleField("replicas");
    await configDialog.toggleField("namespace");
    await configDialog.save();

    const selectedAddon = specPage.getSelectedAddon("platform", "cert-manager");
    await expect(selectedAddon.getByText(/2 overrideable/i)).toBeVisible();
  });
});
