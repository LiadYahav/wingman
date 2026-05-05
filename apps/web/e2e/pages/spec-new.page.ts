import { Page, Locator } from "@playwright/test";

export class SpecNewPage {
  readonly page: Page;
  readonly nameInput: Locator;
  readonly displayNameInput: Locator;
  readonly descriptionInput: Locator;
  readonly addonSearch: Locator;
  readonly submitButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.nameInput = page.getByTestId("spec-name-input");
    this.displayNameInput = page.getByTestId("spec-display-name-input");
    this.descriptionInput = page.getByTestId("spec-description-input");
    this.addonSearch = page.getByPlaceholder("Search addons");
    this.submitButton = page.getByRole("button", { name: /create spec/i });
  }

  async goto() {
    await this.page.goto("/specs/new");
  }

  async fillBasicInfo(name: string, displayName: string, description?: string) {
    await this.nameInput.fill(name);
    await this.displayNameInput.fill(displayName);
    if (description) {
      await this.descriptionInput.fill(description);
    }
  }

  getAddonCard(team: string, name: string): Locator {
    return this.page.getByTestId(`addon-card-${team}-${name}`);
  }

  getSelectedAddon(team: string, name: string): Locator {
    return this.page.getByTestId(`selected-addon-${team}-${name}`);
  }

  async selectAddon(team: string, name: string) {
    await this.getAddonCard(team, name).click();
  }

  async searchAddons(query: string) {
    await this.addonSearch.fill(query);
  }

  async openConfigureDialog(team: string, name: string) {
    const selectedAddon = this.getSelectedAddon(team, name);
    await selectedAddon.getByRole("button", { name: /configure/i }).click();
  }

  async submit() {
    await this.submitButton.click();
  }
}
