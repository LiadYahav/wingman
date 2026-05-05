import { Page, Locator } from "@playwright/test";

export class ClusterNewPage {
  readonly page: Page;
  readonly nameInput: Locator;
  readonly specSelect: Locator;
  readonly mceSelect: Locator;
  readonly siteSelect: Locator;
  readonly submitButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.nameInput = page.getByTestId("cluster-name-input");
    this.specSelect = page.getByTestId("spec-select");
    this.mceSelect = page.getByTestId("mce-select");
    this.siteSelect = page.getByTestId("site-select");
    this.submitButton = page.getByRole("button", { name: /create cluster/i });
  }

  async goto() {
    await this.page.goto("/clusters/new");
  }

  getOverrideField(path: string): Locator {
    const testId = `override-field-${path.replace(/\./g, "-")}`;
    return this.page.getByTestId(testId);
  }

  async fillClusterName(name: string) {
    await this.nameInput.fill(name);
  }

  async selectSpec(specName: string) {
    await this.specSelect.click();
    await this.page.getByRole("option", { name: specName }).click();
  }

  async selectMce(mceName: string) {
    await this.mceSelect.click();
    await this.page.getByRole("option", { name: mceName }).click();
  }

  async selectSite(siteName: string) {
    await this.siteSelect.click();
    await this.page.getByRole("option", { name: siteName }).click();
  }

  async setOverrideValue(path: string, value: string) {
    const field = this.getOverrideField(path);
    await field.fill(value);
  }

  async toggleBooleanOverride(path: string) {
    const field = this.getOverrideField(path);
    await field.click();
  }

  async submit() {
    await this.submitButton.click();
  }
}
