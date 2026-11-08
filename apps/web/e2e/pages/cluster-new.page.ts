import { Page, Locator } from "@playwright/test";

/** The two-step create form at /clusters/new: choose a spec, then configure the cluster. */
export class ClusterNewPage {
  readonly page: Page;
  readonly siteSelect: Locator;
  readonly mceSelect: Locator;
  readonly nameInput: Locator;
  readonly namingHint: Locator;
  readonly versionSelect: Locator;
  readonly versionInput: Locator;
  readonly versionSource: Locator;
  readonly offConventionMces: Locator;
  readonly formProblems: Locator;
  readonly reviewButton: Locator;
  readonly reviewDialog: Locator;

  constructor(page: Page) {
    this.page = page;
    this.siteSelect = page.getByTestId("site-select");
    this.mceSelect = page.getByTestId("mce-select");
    this.nameInput = page.getByTestId("cluster-name-input");
    this.namingHint = page.getByTestId("naming-hint");
    this.versionSelect = page.getByTestId("ocp-version-select");
    this.versionInput = page.getByTestId("ocp-version-input");
    this.versionSource = page.getByTestId("ocp-version-source");
    this.offConventionMces = page.getByTestId("off-convention-mces");
    this.formProblems = page.getByTestId("form-problems");
    this.reviewButton = page.getByTestId("review-button");
    // By name: an open (or closing) combobox popup is a dialog too
    this.reviewDialog = page.getByRole("dialog", { name: /^Review/ });
  }

  /** Land on "/" first so the persisted session hydrates, then open the form. */
  async goto() {
    await this.page.goto("/");
    await this.page.waitForLoadState("domcontentloaded");
    await this.page.goto("/clusters/new");
    await this.page.waitForLoadState("domcontentloaded");
  }

  specCard(name: string): Locator {
    return this.page.getByTestId(`spec-card-${name}`);
  }

  async chooseSpec(name: string) {
    await this.specCard(name).click();
  }

  /** An option of the open select popup. */
  option(name: string | RegExp): Locator {
    return this.page.getByRole("option", { name });
  }

  /** An MCE option; its accessible name also carries the env chip. */
  mceOption(mce: string): Locator {
    return this.option(new RegExp(`^${mce.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  }

  async selectSite(site: string) {
    await this.siteSelect.click();
    await this.option(site).click();
  }

  async selectMce(mce: string) {
    await this.mceSelect.click();
    await this.mceOption(mce).click();
  }

  async fillName(name: string) {
    await this.nameInput.fill(name);
  }

  /** A form input of the dynamic template form, by its `e.g. <example>` placeholder. */
  templateInput(example: string): Locator {
    return this.page.getByPlaceholder(`e.g. ${example}`);
  }

  overrideField(team: string, addon: string, path: string): Locator {
    return this.page.getByTestId(`override-field-${team}-${addon}-${path.replace(/\./g, "-")}`);
  }

  async review() {
    await this.reviewButton.click();
  }

  async confirm() {
    await this.reviewDialog.getByRole("button", { name: /confirm/i }).click();
  }
}
