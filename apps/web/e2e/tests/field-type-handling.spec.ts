import { test, expect } from "@playwright/test";
import { openConfigureDialog } from "../pages/configure-dialog.page";
import { mockAllApis } from "../fixtures/api-handlers";

test.describe("Field Type Handling", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("correctly detects array type for arrays", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "external-secrets");

    const secretStoresRow = configDialog.getFieldRow("secretStores");
    // exact: the value summary ("Empty array") also contains "array"
    await expect(secretStoresRow.getByText("array", { exact: true })).toBeVisible();
  });

  test("flattens nested objects into leaf fields", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");

    // Objects are not offered as a whole; each leaf becomes its own dotted path
    await expect(configDialog.getFieldRow("resources.requests")).toHaveCount(0);
    const cpuRow = configDialog.getFieldRow("resources.requests.cpu");
    await expect(cpuRow).toBeVisible();
    await expect(cpuRow.getByText("string", { exact: true })).toBeVisible();
  });

  test("shows correct value summary for arrays", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "observability", "grafana");

    const dashboardsRow = configDialog.getFieldRow("dashboards");
    await expect(dashboardsRow.getByText(/empty array/i)).toBeVisible();
  });

  test("shows value summaries for nested object leaves", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "observability", "grafana");

    await expect(configDialog.getFieldRow("persistence.enabled").getByText("false")).toBeVisible();
    await expect(configDialog.getFieldRow("persistence.size").getByText('"10Gi"')).toBeVisible();
  });

  test("shows correct value summary for booleans", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");

    const installCRDsRow = configDialog.getFieldRow("installCRDs");
    await expect(installCRDsRow.getByText("true")).toBeVisible();
  });

  test("shows correct value summary for integers", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");

    const replicasRow = configDialog.getFieldRow("replicas");
    await expect(replicasRow.getByText("1")).toBeVisible();
  });

  test("shows correct value summary for strings", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");

    const namespaceRow = configDialog.getFieldRow("namespace");
    await expect(namespaceRow.getByText('"cert-manager"')).toBeVisible();
  });

  test("type badge has correct color for each type", async ({ page }) => {
    const { configDialog } = await openConfigureDialog(page, "platform", "cert-manager");

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
