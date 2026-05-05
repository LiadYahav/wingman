import { Page, Locator } from "@playwright/test";

export class SpecEditPage {
  readonly page: Page;
  readonly displayNameInput: Locator;
  readonly descriptionInput: Locator;
  readonly addonSearch: Locator;
  readonly saveButton: Locator;
  readonly deleteButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.displayNameInput = page.getByTestId("spec-display-name-input");
    this.descriptionInput = page.getByTestId("spec-description-input");
    this.addonSearch = page.getByPlaceholder("Search addons");
    this.saveButton = page.getByRole("button", { name: /save changes/i });
    this.deleteButton = page.getByRole("button", { name: /delete/i });
  }

  async goto(specName: string) {
    await this.page.goto(`/specs/${specName}/edit`);
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

  async removeAddon(team: string, name: string) {
    const selectedAddon = this.getSelectedAddon(team, name);
    await selectedAddon.getByRole("button", { name: /remove/i }).click();
  }

  async openConfigureDialog(team: string, name: string) {
    const selectedAddon = this.getSelectedAddon(team, name);
    await selectedAddon.getByRole("button", { name: /configure/i }).click();
  }

  async save() {
    await this.saveButton.click();
  }

  async hasUnsavedChanges(): Promise<boolean> {
    const button = this.saveButton;
    return !(await button.isDisabled());
  }
}
