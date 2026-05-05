import { Page, Locator } from "@playwright/test";

export class ConfigureDialogPage {
  readonly page: Page;
  readonly dialog: Locator;
  readonly saveButton: Locator;
  readonly cancelButton: Locator;
  readonly selectedCount: Locator;
  readonly noFieldsMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.dialog = page.getByRole("dialog");
    this.saveButton = page.getByTestId("save-config-button");
    this.cancelButton = page.getByRole("button", { name: /cancel/i });
    this.selectedCount = page.getByTestId("selected-count");
    this.noFieldsMessage = page.getByTestId("no-fields-message");
  }

  async waitForOpen() {
    await this.dialog.waitFor({ state: "visible" });
  }

  async waitForClose() {
    await this.dialog.waitFor({ state: "hidden" });
  }

  getFieldRow(path: string): Locator {
    const testId = `field-row-${path.replace(/\./g, "-")}`;
    return this.page.getByTestId(testId);
  }

  getFieldCheckbox(path: string): Locator {
    const testId = `field-checkbox-${path.replace(/\./g, "-")}`;
    return this.page.getByTestId(testId);
  }

  getFieldTypeSelect(path: string): Locator {
    const testId = `field-type-${path.replace(/\./g, "-")}`;
    return this.page.getByTestId(testId);
  }

  getFieldHelpInput(path: string): Locator {
    const testId = `field-help-${path.replace(/\./g, "-")}`;
    return this.page.getByTestId(testId);
  }

  async toggleField(path: string) {
    await this.getFieldRow(path).click();
  }

  async selectFieldType(path: string, type: string) {
    await this.getFieldTypeSelect(path).click();
    await this.page.getByRole("option", { name: type }).click();
  }

  async setFieldHelp(path: string, helpText: string) {
    await this.getFieldHelpInput(path).fill(helpText);
  }

  async configureField(path: string, options: { type?: string; help?: string }) {
    await this.toggleField(path);
    if (options.type) {
      await this.selectFieldType(path, options.type);
    }
    if (options.help) {
      await this.setFieldHelp(path, options.help);
    }
  }

  async save() {
    await this.saveButton.click();
    await this.waitForClose();
  }

  async cancel() {
    await this.cancelButton.click();
    await this.waitForClose();
  }

  async getSelectedFieldCount(): Promise<number> {
    const text = await this.selectedCount.textContent();
    const match = text?.match(/(\d+)/);
    return match ? parseInt(match[1], 10) : 0;
  }
}
