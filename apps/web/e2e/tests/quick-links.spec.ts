/**
 * Quick Links (mocked; docs/notes/2026-11-12-quick-links-api.md, ADR-0052):
 * the hub and every MCE with their ArgoCD and console, then the team's links
 * from the links file, in sections with their own column counts. A search
 * filters as you type (`/` focuses it, Escape clears it). Each link's dot is
 * day1's check, with its reason in words; an ArgoCD with a token shows its
 * applications' counts. Admins only: the sidebar hides the entry from a
 * viewer, and day1's 403 says it is for admins.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go } from "../fixtures/api-handlers";
import {
  HUB, MCE_A, MCE_B, MCE_C, SECTIONS, argocdUrl, consoleUrl, forbidden, mockQuickLinks, mockStatus, setUpQuickLinks,
} from "../fixtures/quick-links";

const card = (page: Page, id: string) => page.locator(`[data-card="${id}"]`);
const section = (page: Page, id: string) => page.locator(`[data-section="${id}"]`);
const dot = (page: Page, ping: string) => page.locator(`[data-testid="status-dot"][data-ping="${ping}"]`);
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
    await setUpQuickLinks(page, { viewer: true, board: forbidden, status: forbidden });
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
    await go(page, "/quick-links");
    const sections = page.getByTestId("quick-link-section");
    await expect(sections).toHaveCount(SECTIONS.length);
    await expect(sections.locator("h2")).toHaveText(["Hub", "MCEs in site1", "MCEs in site2", "Core GitOps", "DC Systems"]);
    await expect(section(page, "file:core-gitops")).toHaveAttribute("data-columns", "2");
    await expect(section(page, "file:dc-systems")).toHaveAttribute("data-columns", "3");
    await expect(page.getByTestId("quick-links-summary")).toHaveText(/^9 links in 5 sections\./);

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
    // No ping: no dot
    await expect(card(page, "file:dc-systems:runbooks").getByTestId("status-dot")).toHaveCount(0);
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

  test("each dot is day1's check, with its reason; a link that is not up says why", async ({ page }) => {
    const gitlab = "https://gitlab.example.internal";
    const netbox = "https://netbox.example.internal";
    await setUpQuickLinks(page, {
      status: mockStatus(SECTIONS, {
        checks: {
          [consoleUrl(MCE_B)]: { state: "down", reason: "no answer within 3 s", http_status: null, latency_ms: null },
          [netbox]: { state: "unknown", reason: "TLS certificate not trusted", http_status: null, latency_ms: null },
        },
      }),
    });
    await go(page, "/quick-links");

    await expect(dot(page, argocdUrl(HUB))).toHaveAttribute("data-state", "up");
    await expect(dot(page, argocdUrl(HUB))).toHaveAttribute("aria-label", /^Up · answered 200 in 84 ms · checked .+ ago$/);
    await expect(dot(page, gitlab)).toHaveAttribute("data-state", "up");

    const down = dot(page, consoleUrl(MCE_B));
    await expect(down).toHaveAttribute("data-state", "down");
    await expect(down).toHaveAttribute("aria-label", /^Down · no answer within 3 s · checked/);
    await expect(card(page, `cluster:${MCE_B}`).getByTestId("quick-link-trouble")).toContainText("Console: Down · no answer within 3 s");

    await expect(dot(page, netbox)).toHaveAttribute("data-state", "unknown");
    await expect(card(page, "file:dc-systems:netbox").getByTestId("quick-link-trouble")).toContainText("Unknown · TLS certificate not trusted");

    // The reason on hover, too
    await card(page, `cluster:${MCE_B}`).getByTestId("quick-link-chip").nth(1).hover();
    await expect(page.getByTestId("status-tip")).toContainText("Down · no answer within 3 s");
  });

  test("dots are hollow until day1's checks arrive", async ({ page }) => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    await setUpQuickLinks(page, {
      status: async (route) => {
        await gate;
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockStatus()) });
      },
    });
    await go(page, "/quick-links");
    await expect(dot(page, argocdUrl(HUB))).toHaveAttribute("data-state", "pending");
    await expect(dot(page, argocdUrl(HUB))).toHaveAttribute("aria-label", "Not checked yet");
    await expect(card(page, `cluster:${HUB}`).getByTestId("argocd-widget-loading")).toBeVisible();
    release();
    await expect(dot(page, argocdUrl(HUB))).toHaveAttribute("data-state", "up");
  });

  test("an ArgoCD with a token shows its applications' counts; a failed read says why", async ({ page }) => {
    await setUpQuickLinks(page);
    await go(page, "/quick-links");
    const hub = card(page, `cluster:${HUB}`).getByTestId("argocd-widget");
    await expect(hub.getByTestId("argocd-applications")).toHaveText("45");
    await expect(hub.getByTestId("argocd-synced")).toContainText("42");
    await expect(hub.getByTestId("argocd-out-of-sync")).toContainText("3");
    await expect(hub.getByTestId("argocd-healthy")).toContainText("40");
    await expect(hub.getByTestId("argocd-progressing")).toContainText("1");
    await expect(hub.getByTestId("argocd-degraded")).toContainText("2");
    await expect(hub.getByTestId("argocd-missing")).toContainText("1");

    await expect(card(page, `cluster:${MCE_A}`).getByTestId("argocd-out-of-sync")).toContainText("0");
    // No token for this MCE: a link and its dots, no widget
    await expect(card(page, `cluster:${MCE_B}`).getByTestId("argocd-widget")).toHaveCount(0);
    // A token the instance refused
    await expect(card(page, "file:core-gitops:argocd-main").getByTestId("argocd-widget-error")).toHaveText(
      "Counts unavailable: ArgoCD refused the token (401)"
    );
  });

  test("the links file's problems are listed, and every other section still shows", async ({ page }) => {
    const board = mockQuickLinks({
      sections: SECTIONS.filter((s) => s.id !== "file:dc-systems"),
      problems: ["Set QUICK_LINKS_DOMAIN (or MCE_API_DOMAIN) to list each MCE's ArgoCD and console."],
      links_file: {
        path: "/etc/wingman/quick-links/links.yaml",
        state: "loaded",
        problems: ['sections[1] "DC Systems" links[0] "NetBox": url must be an http(s) URL'],
      },
    });
    await setUpQuickLinks(page, { board, status: mockStatus(board.sections) });
    await go(page, "/quick-links");
    const problems = page.getByTestId("quick-links-problems");
    await expect(problems).toContainText("The links file has problems; the rest is shown.");
    await expect(problems).toContainText('links[0] "NetBox": url must be an http(s) URL');
    await expect(problems).toContainText("Set QUICK_LINKS_DOMAIN");
    await expect(page.getByTestId("quick-link-section")).toHaveCount(4);
  });

  test("an unreadable links file is a warning, never a broken page", async ({ page }) => {
    const board = mockQuickLinks({
      sections: SECTIONS.filter((s) => s.generated),
      links_file: { path: "/etc/wingman/quick-links/links.yaml", state: "invalid", problems: [] },
    });
    await setUpQuickLinks(page, { board, status: mockStatus(board.sections) });
    await go(page, "/quick-links");
    await expect(page.getByTestId("quick-links-problems")).toContainText("/etc/wingman/quick-links/links.yaml could not be read.");
    await expect(page.getByTestId("quick-link-section")).toHaveCount(3);
  });

  test("with nothing configured, it says what to set", async ({ page }) => {
    await setUpQuickLinks(page, {
      board: mockQuickLinks({ sections: [], links_file: { path: "/etc/wingman/quick-links/links.yaml", state: "missing", problems: [] } }),
      status: mockStatus([]),
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
