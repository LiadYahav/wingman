/**
 * The Server Scan area's Rules & Policies page (mocked;
 * docs/notes/2026-11-13-server-scan-area-api.md §13, ADR-0048's 3.30.0
 * amendment): server-scan's classification rules in its order and words, its
 * health policies grouped by scope and sorted by severity, a condition as one
 * line, read only with no control; each section's states on its own.
 */

import { test, expect, type Page } from "@playwright/test";
import { go, held } from "../fixtures/api-handlers";
import { failing, forbidden, off } from "../fixtures/server-scan";
import { POLICIES, RULES, setUpRules } from "../fixtures/server-scan-rules";

const PAGE = "/server-scan/rules";
const scanNav = (page: Page) => page.getByRole("navigation", { name: "Server Scan" });
const rulesTable = (page: Page) => page.getByRole("table", { name: "Classification rules" });
const rule = (page: Page, id: string) => page.locator(`[data-testid="ss-rule"][data-rule="${id}"]`);
const sections = (page: Page) => page.getByTestId("ss-policy-section");
const problem = (page: Page, text: string) => page.getByRole("alert").filter({ hasText: text });

test.describe("The Rules & Policies page", () => {
  test("the sidebar's Rules & Policies, after Servers, opens both sections", async ({ page }) => {
    await setUpRules(page);
    await go(page, "/server-scan");
    await expect(scanNav(page).getByRole("link")).toHaveText(["Sites", "Servers", "Confs", "Events", "Jobs", "Rules & Policies", "Claude", "Architecture"]);
    await scanNav(page).getByRole("link", { name: "Rules & Policies" }).click();
    await expect(page).toHaveURL(/\/server-scan\/rules$/);
    await expect(scanNav(page).getByTestId("area-nav-rules")).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 1, name: "Rules & Policies" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(["Classification rules", "Health policies"]);
    const about = page.getByTestId("ss-rules-about");
    await expect(about).toHaveAccessibleName("About Rules & Policies");
    await about.hover();
    await expect(page.locator("[data-slot=tooltip-content][data-open]")).toContainText("defined in code and seeded at startup, not created here");
  });

  test("the classification rules in server-scan's order, columns and words", async ({ page }) => {
    await setUpRules(page);
    await go(page, PAGE);
    await expect(rulesTable(page).locator("thead th")).toHaveText(["Name", "Type", "Matches", "Priority", "Scope"]);
    await expect(page.getByTestId("ss-rule").locator("td:first-child")).toHaveText(RULES.items.map((r) => r.name));
    const hc = rule(page, "rule-hc");
    await expect(hc.locator("td")).toHaveText([
      "Hosted cluster nodes", "HOSTED_CLUSTER", "name ~ ^ocp-[a-z]+-[a-z0-9]+-site(case-insensitive)", "100", "(unscoped)",
    ]);
    // A case-sensitive, scoped rule: no "(case-insensitive)", its scope in server-scan's words
    const lab = rule(page, "rule-lab");
    await expect(lab.locator("td")).toHaveText(["Lab nodes in Tel Aviv", "HOSTED_CLUSTER", "name ~ ^lab-", "500", "vendor=dell, manager=OPENMANAGE, site=tlv"]);
    // A rule's description is its name's tooltip
    await expect(hc.locator("td").first()).toHaveAttribute("title", "Hosted-cluster nodes, named after their hardware spec and site.");
    await expect(lab.locator("td").first()).not.toHaveAttribute("title", /.*/);
  });

  test("the health policies by scope, General first; by severity, then name; a condition as one line", async ({ page }) => {
    await setUpRules(page);
    await go(page, PAGE);
    await expect(sections(page).getByRole("heading", { level: 3 })).toHaveText(["General", "Dell", "Cisco — UCS Central, Intersight", "Site tlv"]);
    const general = page.getByRole("region", { name: "General", exact: true });
    await expect(general).toContainText("Applies to every server, whatever collected it.");
    await expect(page.getByRole("region", { name: "Dell", exact: true })).not.toContainText("Applies to every server");
    await expect(general.locator("thead th")).toHaveText(["Name", "Category", "Severity", "Condition", "policy_key"]);
    await expect(general.getByTestId("ss-policy").locator("td:first-child")).toHaveText(["Power supply failed", "general major", "general warning"]);
    await expect(general.getByTestId("ss-policy").first().locator("td")).toHaveText([
      "Power supply failed", "storage", "◆Critical",
      "(power.failed_psu_count GTE 2 OR power.failed_psu_count EQ 1 AND power.psu_count LTE 1)", "key.p3",
    ]);
    await expect(general.getByTestId("ss-policy").nth(1).locator("td").nth(3)).toHaveText('NOT raid.state EQ "ABSENT"');
    await expect(general.getByTestId("ss-policy").nth(2).locator("td").nth(2)).toHaveText("▲Warning");
    // A policy's description and message are its name's tooltip
    await expect(general.getByTestId("ss-policy").first().locator("td").first()).toHaveAttribute(
      "title",
      "Power supply failed: why it fires.\nSays: {bad} of {total} failed"
    );
    await expect(page.getByTestId("ss-policy")).toHaveCount(POLICIES.items.length);
  });

  test("read only: nothing to press but the heading's tooltip, no link, field or dropdown", async ({ page }) => {
    await setUpRules(page);
    await go(page, PAGE);
    await expect(page.getByTestId("ss-rule")).toHaveCount(4);
    const main = page.getByRole("main");
    await expect(main.getByRole("button")).toHaveCount(1);
    await expect(main.getByRole("button")).toHaveAccessibleName("About Rules & Policies");
    await expect(main.getByRole("link")).toHaveCount(0);
    await expect(main.getByRole("textbox")).toHaveCount(0);
    await expect(main.getByRole("combobox")).toHaveCount(0);
    await expect(main).not.toContainText(/new rule|new policy/i);
    // Enabled only, so no status column (the intro may say "disabled": it is server-scan's text)
    await expect(main.getByText(/^(enabled|disabled)$/i)).toHaveCount(0);
  });
});

test.describe("The Rules & Policies page's states", () => {
  test("each section shows skeleton rows until its own answer comes", async ({ page }) => {
    const rules = held();
    await setUpRules(page, { rules: rules.answer(RULES) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-rules-loading")).toBeVisible();
    await expect(page.getByTestId("ss-policy")).toHaveCount(POLICIES.items.length);
    rules.release();
    await expect(page.getByTestId("ss-rule")).toHaveCount(4);
    await expect(page.getByTestId("ss-rules-loading")).toHaveCount(0);
  });

  test("none of either: server-scan's words", async ({ page }) => {
    await setUpRules(page, { rules: { items: [] }, policies: { items: [] } });
    await go(page, PAGE);
    await expect(rulesTable(page)).toContainText("No classification rules are configured.");
    await expect(page.getByTestId("ss-policies-none")).toHaveText("No health policies are configured.");
  });

  test("one read failing shows its problem, and the other section still shows", async ({ page }) => {
    await setUpRules(page, { policies: failing });
    await go(page, PAGE);
    await expect(problem(page, "The health policies could not be loaded from server-scan")).toContainText("server-scan unreachable");
    await expect(page.getByTestId("ss-rule")).toHaveCount(4);
    await expect(page.getByTestId("ss-policy")).toHaveCount(0);
  });

  test("without server-scan the page says how to set it up", async ({ page }) => {
    await setUpRules(page, { rules: off, policies: off, sites: off });
    await page.goto(PAGE);
    await expect(page.getByTestId("ss-off")).toContainText("serverScan.url");
    await expect(rulesTable(page)).toHaveCount(0);
  });

  test("a viewer is told it is for admins", async ({ page }) => {
    await setUpRules(page, { rules: forbidden, policies: forbidden, sites: forbidden, viewer: true });
    await page.goto(PAGE);
    await expect(page.getByTestId("ss-forbidden")).toBeVisible();
    await expect(rulesTable(page)).toHaveCount(0);
  });

  test("not polled: opening the page again within 30 seconds reads nothing new", async ({ page }) => {
    const { reads } = await setUpRules(page);
    await go(page, PAGE);
    await expect(page.getByTestId("ss-rule")).toHaveCount(4);
    await expect(page.getByTestId("ss-policy")).toHaveCount(POLICIES.items.length);
    const after = reads();
    await scanNav(page).getByRole("link", { name: "Sites" }).click();
    await expect(page).toHaveURL(/\/server-scan$/);
    await scanNav(page).getByRole("link", { name: "Rules & Policies" }).click();
    await expect(page.getByTestId("ss-rule")).toHaveCount(4);
    expect(reads()).toBe(after);
  });
});
