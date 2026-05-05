import { test, expect } from "@playwright/test";
import { SpecNewPage } from "../pages/spec-new.page";
import { mockAllApis } from "../fixtures/api-handlers";

test.describe("Addon Reordering", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("can add multiple addons in sequence", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.selectAddon("platform", "cert-manager");
    await specPage.selectAddon("observability", "prometheus");
    await specPage.selectAddon("networking", "ingress-nginx");

    await expect(specPage.getSelectedAddon("platform", "cert-manager")).toBeVisible();
    await expect(specPage.getSelectedAddon("observability", "prometheus")).toBeVisible();
    await expect(specPage.getSelectedAddon("networking", "ingress-nginx")).toBeVisible();
  });

  test("shows drag handles on selected addons", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.selectAddon("platform", "cert-manager");
    await specPage.selectAddon("observability", "prometheus");

    const certManager = specPage.getSelectedAddon("platform", "cert-manager");
    await expect(certManager.locator("[data-testid='drag-handle']")).toBeVisible();
  });

  test("shows order numbers on selected addons", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.selectAddon("platform", "cert-manager");
    await specPage.selectAddon("observability", "prometheus");
    await specPage.selectAddon("networking", "ingress-nginx");

    const certManager = specPage.getSelectedAddon("platform", "cert-manager");
    const prometheus = specPage.getSelectedAddon("observability", "prometheus");
    const ingress = specPage.getSelectedAddon("networking", "ingress-nginx");

    await expect(certManager.getByText("1")).toBeVisible();
    await expect(prometheus.getByText("2")).toBeVisible();
    await expect(ingress.getByText("3")).toBeVisible();
  });

  test("updates order numbers after drag and drop", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.selectAddon("platform", "cert-manager");
    await specPage.selectAddon("observability", "prometheus");

    const certManager = specPage.getSelectedAddon("platform", "cert-manager");
    const prometheus = specPage.getSelectedAddon("observability", "prometheus");

    const certHandle = certManager.locator("[data-testid='drag-handle']");
    const prometheusBounds = await prometheus.boundingBox();

    if (prometheusBounds) {
      await certHandle.dragTo(prometheus, {
        targetPosition: { x: prometheusBounds.width / 2, y: prometheusBounds.height + 10 },
      });
    }

    await expect(prometheus.getByText("1")).toBeVisible();
    await expect(certManager.getByText("2")).toBeVisible();
  });

  test("five addons display without collision", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.selectAddon("platform", "cert-manager");
    await specPage.selectAddon("platform", "external-secrets");
    await specPage.selectAddon("observability", "prometheus");
    await specPage.selectAddon("observability", "grafana");
    await specPage.selectAddon("networking", "ingress-nginx");

    const addons = [
      specPage.getSelectedAddon("platform", "cert-manager"),
      specPage.getSelectedAddon("platform", "external-secrets"),
      specPage.getSelectedAddon("observability", "prometheus"),
      specPage.getSelectedAddon("observability", "grafana"),
      specPage.getSelectedAddon("networking", "ingress-nginx"),
    ];

    for (const addon of addons) {
      await expect(addon).toBeVisible();
    }

    const bounds = await Promise.all(addons.map((a) => a.boundingBox()));
    for (let i = 0; i < bounds.length; i++) {
      for (let j = i + 1; j < bounds.length; j++) {
        const b1 = bounds[i];
        const b2 = bounds[j];
        if (b1 && b2) {
          const overlapsY = !(b1.y + b1.height <= b2.y || b2.y + b2.height <= b1.y);
          const overlapsX = !(b1.x + b1.width <= b2.x || b2.x + b2.width <= b1.x);
          expect(overlapsX && overlapsY).toBe(false);
        }
      }
    }
  });
});
