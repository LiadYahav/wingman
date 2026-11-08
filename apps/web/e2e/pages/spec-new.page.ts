import { expect, Page, Locator } from "@playwright/test";

export class SpecNewPage {
  readonly page: Page;
  readonly nameInput: Locator;
  readonly versionInput: Locator;
  readonly descriptionInput: Locator;
  readonly addonSearch: Locator;
  readonly submitButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.nameInput = page.getByTestId("spec-name-input");
    this.versionInput = page.getByTestId("spec-version-input");
    this.descriptionInput = page.getByTestId("spec-description-input");
    this.addonSearch = page.getByRole("textbox", { name: "Search addons" });
    this.submitButton = page.getByRole("button", { name: /review & create/i });
  }

  async goto() {
    // Visit "/" first so Zustand's async persist hydration picks up the
    // injected auth before we land on the target route (see injectAdminAuth).
    await this.page.goto("/");
    await this.page.goto("/specs/new");
  }

  async fillBasicInfo(name: string, version?: string) {
    await this.nameInput.fill(name);
    if (version) {
      await this.versionInput.fill(version);
    }
  }

  /**
   * Choose the hardware type of the first nodepool's `nm-conf`: a new flavor's
   * nodepool starts with the nodepool defaults, and day1 refuses a flavor's
   * `nm-conf` without one (flavors v2, §3).
   */
  async chooseNetworkHardware(hardware = "dell", nodepool = 0) {
    await this.page
      .getByTestId(`nodepool-${nodepool}-configs`)
      .getByRole("combobox", { name: /entry 1 hardware type$/ })
      .click();
    await this.page.getByRole("option").filter({ has: this.page.getByText(hardware, { exact: true }) }).click();
    // The list is a popup (role dialog) until its exit animation ends
    await expect(this.page.getByRole("option")).toHaveCount(0);
  }

  getTeamHeader(team: string): Locator {
    return this.page.getByRole("button", { name: new RegExp(`^${team}`) });
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

  /** Open the review dialog and confirm the create MR. */
  async reviewAndConfirm() {
    await this.submitButton.click();
    await this.page.getByRole("dialog").getByRole("button", { name: /confirm/i }).click();
  }
}
