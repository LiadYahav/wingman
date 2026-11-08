import { Page, Locator } from "@playwright/test";

export class SpecEditPage {
  readonly page: Page;
  readonly versionInput: Locator;
  readonly descriptionInput: Locator;
  readonly addonSearch: Locator;
  readonly reviewButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.versionInput = page.getByTestId("spec-version-input");
    this.descriptionInput = page.getByTestId("spec-description-input");
    this.addonSearch = page.getByRole("textbox", { name: "Search addons" });
    this.reviewButton = page.getByRole("button", { name: /review & update/i });
  }

  async goto(specName: string) {
    // Visit "/" first so Zustand's async persist hydration picks up the
    // injected auth before we land on the target route (see injectAdminAuth).
    await this.page.goto("/");
    await this.page.waitForLoadState("domcontentloaded");
    await this.page.goto(`/specs/${specName}/edit`);
    await this.page.waitForLoadState("domcontentloaded");
  }

  getAddonCard(team: string, name: string): Locator {
    return this.page.getByTestId(`addon-card-${team}-${name}`);
  }

  getSelectedAddon(team: string, name: string): Locator {
    return this.page.getByTestId(`selected-addon-${team}-${name}`);
  }

  async selectAddon(team: string, name: string) {
    await this.getAddonCard(team, name).getByRole("button", { name: "Add", exact: true }).click();
  }

  async removeAddon(team: string, name: string) {
    await this.getSelectedAddon(team, name).getByRole("button", { name: /remove/i }).click();
  }

  async openConfigureDialog(team: string, name: string) {
    await this.getSelectedAddon(team, name).getByRole("button", { name: /configure/i }).click();
  }

  /** Open the review dialog and confirm the update MR. */
  async reviewAndConfirm() {
    await this.reviewButton.click();
    await this.page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
  }
}
