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

    // exact: the version picker ("1.12.0", "2.45.0") also contains these digits
    await expect(certManager.getByText("1", { exact: true })).toBeVisible();
    await expect(prometheus.getByText("2", { exact: true })).toBeVisible();
    await expect(ingress.getByText("3", { exact: true })).toBeVisible();
  });

  test("updates order numbers after drag and drop", async ({ page }) => {
    const specPage = new SpecNewPage(page);
    await specPage.goto();

    await specPage.selectAddon("platform", "cert-manager");
    await specPage.selectAddon("observability", "prometheus");

    const certManager = specPage.getSelectedAddon("platform", "cert-manager");
    const prometheus = specPage.getSelectedAddon("observability", "prometheus");
    // The add-ons are the flavor page's third part: bring the list to the middle of the screen
    // (clear of the sticky bar of parts) before dragging in it
    await certManager.evaluate((el) => el.scrollIntoView({ block: "center" }));

    const handleBounds = await certManager.locator("[data-testid='drag-handle']").boundingBox();
    const prometheusBounds = await prometheus.boundingBox();
    expect(handleBounds).not.toBeNull();
    expect(prometheusBounds).not.toBeNull();

    // dnd-kit's PointerSensor needs intermediate pointer moves; a single-jump
    // dragTo() never registers a drag, so move in steps past prometheus.
    const startX = handleBounds!.x + handleBounds!.width / 2;
    const startY = handleBounds!.y + handleBounds!.height / 2;
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX, startY + 5, { steps: 5 });
    await page.mouse.move(startX, prometheusBounds!.y + prometheusBounds!.height + 10, { steps: 20 });
    await page.mouse.up();

    await expect(prometheus.getByText("1", { exact: true })).toBeVisible();
    await expect(certManager.getByText("2", { exact: true })).toBeVisible();
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
