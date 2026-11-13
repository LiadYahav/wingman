/**
 * Quick Links (mocked; docs/notes/2026-11-12-quick-links-api.md, ADR-0052):
 * the hub and every MCE with their ArgoCD and console, then the team's links
 * from the links file, in sections with their own column counts. A search
 * filters as you type (`/` focuses it, Escape clears it). Cards are links
 * only: no status checks, no ArgoCD counts (ADR-0052's 2026-11-13
 * amendment). Admins only: the sidebar hides the entry from a viewer, and
 * day1's 403 says it is for admins.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go } from "../fixtures/api-handlers";
import {
  MCE_A, MCE_C, SECTIONS, argocdUrl, consoleUrl, forbidden, mockQuickLinks, setUpQuickLinks,
} from "../fixtures/quick-links";

const card = (page: Page, id: string) => page.locator(`[data-card="${id}"]`);
const section = (page: Page, id: string) => page.locator(`[data-section="${id}"]`);
const search = (page: Page) => page.getByRole("searchbox", { name: "Search links" });

test.describe("Quick Links", () => {
  test("the sidebar has the entry for an admin, and it opens the page", async ({ page }) => {
    await setUpQuickLinks(page);
    await go(page, "/");
    const entry = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Quick Links" });
    await expect(entry).toBeVisible();
    await entry.click();
    await expect(page).toHaveURL(/\/quick-links$/);
    await expect(page.getByRole("heading", { level: 1, name: "Quick Links" })).toBeVisible();
    await expect(entry).toHaveAttribute("aria-current", "page");
  });

  test("a viewer has no entry, and the page says it is for admins", async ({ page }) => {
    await setUpQuickLinks(page, { viewer: true, board: forbidden });
    await go(page, "/");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link", { name: "Clusters" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Quick Links" })).toHaveCount(0);
    await page.goto("/quick-links");
    await expect(page.getByTestId("quick-links-forbidden")).toContainText("For admins");
    await expect(search(page)).toHaveCount(0);
  });

  test("sections in order, with their cards and column counts", async ({ page }) => {
    await setUpQuickLinks(page);
    // The page reads the cards and nothing else of day1's Quick Links
    const reads: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith("/api/day1/quick-links")) reads.push(path);
    });
    await go(page, "/quick-links");
    const sections = page.getByTestId("quick-link-section");
    await expect(sections).toHaveCount(SECTIONS.length);
    await expect(sections.locator("h2")).toHaveText(["Hub", "MCEs in site1", "MCEs in site2", "Core GitOps", "DC Systems"]);
    await expect(section(page, "file:core-gitops")).toHaveAttribute("data-columns", "2");
    await expect(section(page, "file:dc-systems")).toHaveAttribute("data-columns", "3");
    await expect(page.getByTestId("quick-links-summary")).toHaveText("9 links in 5 sections.");

    // A generated card: its name, description, and two labelled links, each opening in a new tab
    const mce = card(page, `cluster:${MCE_A}`);
    await expect(mce.getByTestId("quick-link-description")).toHaveText("OpenShift 4.16.27 · 3 hosted clusters");
    const chips = mce.getByTestId("quick-link-chip");
    await expect(chips).toHaveCount(2);
    await expect(chips.nth(0)).toHaveAttribute("href", argocdUrl(MCE_A));
    await expect(chips.nth(1)).toHaveAttribute("href", consoleUrl(MCE_A));
    for (const link of [chips.nth(0), chips.nth(1), mce.getByTestId("quick-link-title")]) {
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    // The title opens the card's own link: the ArgoCD
    await expect(mce.getByTestId("quick-link-title")).toHaveAttribute("href", argocdUrl(MCE_A));

    // Icons by key, shipped with Wingman; an unknown key shows the generic link
    await expect(card(page, "file:core-gitops:gitlab-gitops-project").getByTestId("quick-link-icon")).toHaveAttribute("data-icon", "gitlab");
    await expect(card(page, "file:dc-systems:openmanage").getByTestId("quick-link-icon")).toHaveAttribute("data-icon", "dell");
    await expect(card(page, "file:dc-systems:runbooks").getByTestId("quick-link-icon")).toHaveAttribute("data-icon", "link");
    // A file card is its title only: no chips
    await expect(card(page, "file:dc-systems:runbooks").getByTestId("quick-link-chip")).toHaveCount(0);
    await expect(card(page, "file:dc-systems:runbooks").getByTestId("quick-link-title")).toHaveAttribute("href", "https://wiki.example.internal/runbooks");

    expect(new Set(reads)).toEqual(new Set(["/api/day1/quick-links"]));
  });

  test("search filters as you type, hides empty sections, and says when nothing matches", async ({ page }) => {
    await setUpQuickLinks(page);
    await go(page, "/quick-links");
    await expect(page.getByTestId("quick-link-card")).toHaveCount(9);

    // `/` focuses the search from the page
    await page.locator("body").click();
    await page.keyboard.press("/");
    await expect(search(page)).toBeFocused();

    await page.keyboard.type("site2");
    await expect(page.getByTestId("quick-link-section")).toHaveCount(1);
    await expect(page.getByTestId("quick-link-card")).toHaveCount(1);
    await expect(card(page, `cluster:${MCE_C}`)).toBeVisible();
    await expect(page.getByTestId("quick-links-summary")).toHaveText("1 of 9 links match");

    // A description and a URL match too; every word must match
    await search(page).fill("dell");
    await expect(page.getByTestId("quick-link-card")).toHaveCount(1);
    await expect(card(page, "file:dc-systems:openmanage")).toBeVisible();
    await search(page).fill("gitlab.example.internal");
    await expect(page.getByTestId("quick-link-card")).toHaveCount(1);
    await search(page).fill("prod console");
    await expect(page.getByTestId("quick-link-card")).toHaveCount(3);

    // A section's name keeps all its cards
    await search(page).fill("core gitops");
    await expect(section(page, "file:core-gitops").getByTestId("quick-link-card")).toHaveCount(2);

    await search(page).fill("nothing-like-this");
    await expect(page.getByTestId("quick-links-no-matches")).toBeVisible();
    await expect(page.getByTestId("quick-link-section")).toHaveCount(0);

    // Escape clears it
    await search(page).press("Escape");
    await expect(search(page)).toHaveValue("");
    await expect(page.getByTestId("quick-link-card")).toHaveCount(9);
  });

  test("the links file's problems are listed, and every other section still shows", async ({ page }) => {
    const board = mockQuickLinks({
      sections: SECTIONS.filter((s) => s.id !== "file:dc-systems"),
      problems: ["Set QUICK_LINKS_DOMAIN (or MCE_API_DOMAIN) to list each MCE's ArgoCD and console."],
      links_file: {
        path: "/etc/wingman/quick-links/links.yaml",
        state: "loaded",
        problems: [
          'sections[1] "DC Systems" links[0] "NetBox": url must be an http(s) URL',
          // A file from before 3.13.1: its ping and argocd keys are unknown now
          `sections[0] "Core GitOps" links[1] "ArgoCD Main": unknown key 'argocd', 'ping' (ignored)`,
        ],
      },
    });
    await setUpQuickLinks(page, { board });
    await go(page, "/quick-links");
    const problems = page.getByTestId("quick-links-problems");
    await expect(problems).toContainText("The links file has problems; the rest is shown.");
    await expect(problems).toContainText('links[0] "NetBox": url must be an http(s) URL');
    await expect(problems).toContainText(`"ArgoCD Main": unknown key 'argocd', 'ping' (ignored)`);
    await expect(problems).toContainText("Set QUICK_LINKS_DOMAIN");
    await expect(page.getByTestId("quick-link-section")).toHaveCount(4);
  });

  test("with GitLab down, the MCEs are missing and the hub and the team's links still show", async ({ page }) => {
    const board = mockQuickLinks({
      sections: SECTIONS.filter((s) => !s.id.startsWith("site:")),
      problems: ["The day1 repo could not be read, so its MCEs are missing: GitLab did not answer."],
    });
    await setUpQuickLinks(page, { board });
    await go(page, "/quick-links");
    await expect(page.getByTestId("quick-links-problems")).toContainText("The day1 repo could not be read, so its MCEs are missing");
    await expect(page.getByTestId("quick-link-section").locator("h2")).toHaveText(["Hub", "Core GitOps", "DC Systems"]);
  });

  test("an unreadable links file is a warning, never a broken page", async ({ page }) => {
    const board = mockQuickLinks({
      sections: SECTIONS.filter((s) => s.generated),
      links_file: { path: "/etc/wingman/quick-links/links.yaml", state: "invalid", problems: [] },
    });
    await setUpQuickLinks(page, { board });
    await go(page, "/quick-links");
    await expect(page.getByTestId("quick-links-problems")).toContainText("/etc/wingman/quick-links/links.yaml could not be read.");
    await expect(page.getByTestId("quick-link-section")).toHaveCount(3);
  });

  test("with nothing configured, it says what to set", async ({ page }) => {
    await setUpQuickLinks(page, {
      board: mockQuickLinks({ sections: [], links_file: { path: "/etc/wingman/quick-links/links.yaml", state: "missing", problems: [] } }),
    });
    await go(page, "/quick-links");
    await expect(page.getByTestId("quick-links-empty")).toContainText("No links yet");
    await expect(page.getByTestId("quick-links-empty")).toContainText("QUICK_LINKS_HUB_NAME");
  });

  test("a failed read is shown as day1's problem", async ({ page }) => {
    await setUpQuickLinks(page, {
      board: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "GitLab did not answer reading the day1 repo."),
    });
    await go(page, "/quick-links");
    const alert = page.getByRole("alert").filter({ hasText: "could not be loaded" });
    await expect(alert).toContainText("Quick Links could not be loaded");
    await expect(alert).toContainText("GitLab did not answer reading the day1 repo.");
  });
});
