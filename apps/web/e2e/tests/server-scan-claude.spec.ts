/**
 * The Server Scan area's Claude page (mocked; docs/notes/2026-11-13-server-scan-area-api.md
 * §12, ADR-0048's 3.27.0 amendment): server-scan's guide to its Claude Code
 * skill in Wingman, its words; the download through day1; the commands and
 * the token link naming server-scan, never Wingman; no token made here; the
 * states. Never a live server-scan.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, held } from "../fixtures/api-handlers";
import { forbidden, setUpServerScan } from "../fixtures/server-scan";
import { SERVER_SCAN_URL, mockSkill, setUpSkill } from "../fixtures/server-scan-skill";

const PAGE = "/server-scan/claude";
const MCP = `claude mcp add --transport http server-scan ${SERVER_SCAN_URL}/mcp --header "Authorization: Bearer <your token>"`;
/** Wingman's problem panels (Next's route announcer is an alert too). */
const problem = (page: Page, text: string) => page.getByRole("alert").filter({ hasText: text });

/** Replace the clipboard: `writeText` records what it is given. */
async function stubClipboard(page: Page) {
  await page.addInitScript(() => {
    const copied: string[] = [];
    (window as unknown as { __copied: string[] }).__copied = copied;
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (text: string) => void copied.push(text) },
    });
  });
}

const copied = (page: Page) => page.evaluate(() => (window as unknown as { __copied: string[] }).__copied);

test.describe("The Claude page", () => {
  test("the sidebar's Claude entry opens server-scan's guide, in its words", async ({ page }) => {
    await setUpSkill(page);
    await go(page, "/server-scan");
    const nav = page.getByRole("navigation", { name: "Server Scan" });
    await nav.getByRole("link", { name: "Claude" }).click();
    await expect(page).toHaveURL(/\/server-scan\/claude$/);
    await expect(nav.getByTestId("area-nav-claude")).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 1, name: "Ask Claude about Server Scan" })).toBeVisible();
    await expect(page.getByText("Install the server-scan-api skill in Claude Code and ask in plain language.")).toBeVisible();
    await expect(page.getByRole("main").getByRole("heading", { level: 2 })).toHaveText([
      "Set it up in a minute",
      "Or connect it as an MCP server",
      "When Claude uses it",
      "What it may run",
      "What’s inside",
    ]);
  });

  test("the steps name server-scan's address, its token page and the zip's token line", async ({ page }) => {
    await stubClipboard(page);
    await setUpSkill(page);
    await go(page, PAGE);
    const steps = page.getByRole("region", { name: "Set it up in a minute" });
    await expect(steps.getByRole("heading", { level: 3 })).toHaveText(["Download the zip", "Unzip it into your skills folder", "Add your token", "Ask"]);
    await expect(steps).toContainText(`server-scan's address (${SERVER_SCAN_URL}) is already written into it.`);
    await expect(page.getByTestId("ss-unzip-command")).toHaveText("unzip -o ~/Downloads/server-scan-api.zip -d ~/.claude/skills");
    const token = page.getByTestId("ss-token-link");
    await expect(token).toHaveAttribute("href", `${SERVER_SCAN_URL}/skill`);
    await expect(token).toHaveAttribute("target", "_blank");
    await expect(token).toHaveAttribute("rel", "noopener noreferrer");
    await expect(steps).toContainText("open ~/.claude/skills/server-scan-api/SKILL.md and replace the AUDITOR_TOKEN placeholder. Keep it out of git.");
    await expect(page.getByTestId("ss-token-note")).toHaveText(
      "server-scan makes a personal token only for someone signed in to server-scan itself, so Wingman cannot make yours."
    );
    // No token is made, replaced or revoked here, as server-scan's own page does for its signed-in users
    await expect(page.getByRole("button", { name: /my token|revoke/i })).toHaveCount(0);
    const prompts = page.getByTestId("ss-prompts").getByRole("button");
    await expect(prompts).toHaveText(["“All Dell servers in site1”", "“Which servers are available”"]);
    await prompts.first().click();
    await steps.getByRole("button", { name: /^Copy unzip command/ }).click();
    expect(await copied(page)).toEqual(["All Dell servers in site1", "unzip -o ~/Downloads/server-scan-api.zip -d ~/.claude/skills"]);
  });

  test("a viewer token's copy names VIEWER_TOKEN, and the step says so", async ({ page }) => {
    await setUpSkill(page, { skill: mockSkill({ token_line: "VIEWER_TOKEN" }) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-token-line")).toHaveText("VIEWER_TOKEN");
  });

  test("the MCP command points at server-scan, its token left to paste from server-scan's page", async ({ page }) => {
    await stubClipboard(page);
    await setUpSkill(page);
    await go(page, PAGE);
    const mcp = page.getByRole("region", { name: "Or connect it as an MCP server" });
    await expect(page.getByTestId("ss-mcp-command")).toHaveText(MCP);
    await expect(mcp).toContainText("It uses your token, so it sees only what you may.");
    await expect(page.getByTestId("ss-mcp-token-link")).toHaveAttribute("href", `${SERVER_SCAN_URL}/skill`);
    await mcp.getByRole("button", { name: /^Copy MCP command/ }).click();
    expect(await copied(page)).toEqual([MCP]);
  });

  test("the download is server-scan's zip through day1, with the session's token, saved under the skill's name", async ({ page }) => {
    const calls = await setUpSkill(page);
    await go(page, PAGE);
    const asked = page.waitForRequest("**/api/day1/server-scan/skill/download");
    const [file] = await Promise.all([page.waitForEvent("download"), page.getByTestId("ss-skill-download").click()]);
    expect(file.suggestedFilename()).toBe("server-scan-api.zip");
    expect((await asked).headers()["authorization"]).toMatch(/^Bearer /);
    expect(calls.downloads()).toBe(1);
    await expect(page.getByTestId("ss-skill-download")).toHaveText("Download server-scan-api.zip");
  });

  test("a failed download says so and keeps the page", async ({ page }) => {
    await setUpSkill(page, {
      download: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "server-scan unreachable downloading the Claude skill: ConnectError"),
    });
    await go(page, PAGE);
    await page.getByTestId("ss-skill-download").click();
    await expect(problem(page, "The zip could not be downloaded from server-scan")).toContainText("server-scan unreachable");
    await expect(page.getByTestId("ss-mcp-command")).toBeVisible();
  });

  test("when and what it runs, from the skill's own frontmatter", async ({ page }) => {
    await setUpSkill(page);
    await go(page, PAGE);
    await expect(page.getByText("Also for questions about a server's BMC address.")).toBeVisible();
    await expect(page.getByTestId("ss-skill-tools").locator("span")).toHaveText(["Bash(curl *)", "Bash(jq *)"]);
  });

  test("what's inside: each file a tab, its outline without fenced code, numbered lines", async ({ page }) => {
    await setUpSkill(page);
    await go(page, PAGE);
    const inside = page.getByRole("region", { name: "What’s inside" });
    await expect(inside.getByRole("tab")).toHaveText(["SKILL.md", "references/endpoints.md"]);
    await expect(inside.getByRole("tab", { name: "SKILL.md" })).toHaveAttribute("aria-selected", "true");
    const outline = inside.getByRole("navigation", { name: "On this page" }).getByRole("button");
    await expect(outline).toHaveText(["Connection - edit these two lines for your environment", "Choose the endpoint", "Filters"]);
    await expect(page.getByTestId("ss-skill-lines")).toHaveText("19 lines");
    await expect(inside.getByLabel("SKILL.md", { exact: true })).toContainText("AUDITOR_TOKEN=REPLACE_WITH_AUDITOR_TOKEN");
    await inside.getByRole("tab", { name: "references/endpoints.md" }).click();
    await expect(inside.getByLabel("references/endpoints.md", { exact: true })).toContainText("GET /api/v1/servers");
    await expect(outline).toHaveText(["Servers"]);
  });
});

test.describe("The Claude page's states", () => {
  test("loading, then the guide", async ({ page }) => {
    const answer = held();
    await setUpSkill(page, { skill: answer.answer(mockSkill()) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-skill-loading")).toBeVisible();
    answer.release();
    await expect(page.getByRole("heading", { level: 1, name: "Ask Claude about Server Scan" })).toBeVisible();
    await expect(page.getByTestId("ss-skill-loading")).toHaveCount(0);
  });

  test("a server-scan that carries no skill says so", async ({ page }) => {
    await setUpSkill(page, { skill: (route) => fulfillProblem(route, 404, "NOT_FOUND", "server-scan: This deployment carries no Claude Code skill.") });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-skill-missing")).toContainText("This server-scan carries no skill");
    await expect(page.getByTestId("ss-skill-download")).toHaveCount(0);
  });

  test("server-scan failing shows day1's problem", async ({ page }) => {
    await setUpSkill(page, {
      skill: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "server-scan refused Wingman's token (401) reading the Claude skill: check SERVER_SCAN_TOKEN"),
    });
    await go(page, PAGE);
    await expect(problem(page, "The skill could not be read from server-scan")).toContainText("SERVER_SCAN_TOKEN");
  });

  test("without server-scan the page says how to set it up", async ({ page }) => {
    await setUpSkill(page, {
      skill: (route) => fulfillProblem(route, 501, "FEATURE_DISABLED", "Server Scan is not set up in this deployment: SERVER_SCAN_URL is empty."),
    });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-off")).toContainText("serverScan.url");
  });

  test("a viewer sees that it is for admins, with no Server Scan sidebar", async ({ page }) => {
    await setUpServerScan(page, { viewer: true, sites: forbidden });
    await page.route("**/api/day1/server-scan/skill", forbidden);
    await go(page, PAGE);
    await expect(page.getByTestId("ss-forbidden")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Server Scan" })).toHaveCount(0);
  });
});
