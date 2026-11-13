import { Page, Locator, expect } from "@playwright/test";
import { go } from "../fixtures/api-handlers";

/** Where a cluster goes: the person chooses the site, prod or prep and the version; Wingman picks the MCE. */
export type Place = { site?: string; env: "prod" | "prep"; version: string };

/** The reason the page object gives when a test goes with another MCE than Wingman's pick. */
export const OVERRIDE_REASON = "The test creates its cluster on this MCE";

/**
 * The two-step create form at /clusters/new: choose a spec, then configure the
 * cluster. Its MCE is Wingman's pick from the site, prod or prep and the
 * version (ADR-0050); there is no MCE select.
 */
export class ClusterNewPage {
  readonly page: Page;
  readonly siteSelect: Locator;
  /** The MCE select of before placement: it must not exist. */
  readonly mceSelect: Locator;
  readonly nameInput: Locator;
  readonly namingHint: Locator;
  readonly versionSelect: Locator;
  readonly versionError: Locator;
  readonly versionSource: Locator;
  readonly versionPresetNote: Locator;
  readonly offConventionMces: Locator;
  readonly formProblems: Locator;
  readonly reviewButton: Locator;
  readonly reviewDialog: Locator;
  /** MCE placement (ADR-0050): the environment, the pick, the candidates and the override's reason. */
  readonly envSelect: Locator;
  readonly placement: Locator;
  readonly placementPick: Locator;
  readonly placementPickName: Locator;
  readonly placementReason: Locator;
  /** The open tooltip (the MCE section's reasons, the suggested name's origin); one closing is left out. */
  readonly tooltip: Locator;

  constructor(page: Page) {
    this.page = page;
    this.siteSelect = page.getByTestId("site-select");
    this.mceSelect = page.getByTestId("mce-select");
    this.nameInput = page.getByTestId("cluster-name-input");
    this.namingHint = page.getByTestId("naming-hint");
    this.versionSelect = page.getByTestId("ocp-version-select");
    this.versionError = page.getByTestId("ocp-version-error");
    this.versionSource = page.getByTestId("ocp-version-source");
    this.versionPresetNote = page.getByTestId("ocp-version-preset-note");
    this.offConventionMces = page.getByTestId("off-convention-mces");
    this.formProblems = page.getByTestId("form-problems");
    this.reviewButton = page.getByTestId("review-button");
    // By name: an open (or closing) combobox popup is a dialog too
    this.reviewDialog = page.getByRole("dialog", { name: /^Review/ });
    this.envSelect = page.getByTestId("env-select");
    this.placement = page.getByTestId("mce-placement");
    this.placementPick = page.getByTestId("placement-pick");
    this.placementPickName = page.getByTestId("placement-pick-name");
    this.placementReason = page.getByTestId("placement-reason");
    this.tooltip = page.locator("[data-slot=tooltip-content][data-open]");
  }

  /** prod or prep. */
  async selectEnv(env: "prod" | "prep") {
    // The radio is visually hidden inside its label, which is what a person clicks
    const label = env === "prod" ? "Prod" : "Prep";
    await this.envSelect.locator("label", { hasText: label }).click();
  }

  /** A candidate MCE's row in the placement. */
  candidate(mce: string): Locator {
    return this.page.getByTestId(`placement-candidate-${mce}`);
  }

  /** A candidate's one mark for its checks; its tooltip holds the reasons. */
  candidateState(mce: string): Locator {
    return this.candidate(mce).getByTestId("placement-state");
  }

  /** The radio that chooses a candidate MCE. */
  candidateRadio(mce: string): Locator {
    return this.page.getByRole("radio", { name: mce, exact: true });
  }

  async selectVersion(version: string) {
    await this.versionSelect.click();
    await this.option(version).click();
  }

  /** The site (unless the name gave it), prod or prep, and the version: then Wingman picks the MCE. */
  async place({ site, env, version }: Place) {
    if (site) await this.selectSite(site);
    await this.selectEnv(env);
    await this.selectVersion(version);
  }

  /**
   * Go with `mce`: nothing to do when it is Wingman's pick; otherwise choose it
   * (it must pass every check) and give the reason an override needs.
   */
  async goWith(mce: string, reason = OVERRIDE_REASON) {
    const radio = this.candidateRadio(mce);
    await expect(radio).toBeEnabled();
    if (await radio.isChecked()) return;
    await radio.check();
    await this.placementReason.fill(reason);
  }

  /** Land on "/" first so the persisted session hydrates, then open the form. */
  async goto() {
    await go(this.page, "/clusters/new");
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

  async selectSite(site: string) {
    await this.siteSelect.click();
    await this.option(site).click();
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
