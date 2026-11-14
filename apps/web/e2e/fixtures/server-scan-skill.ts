/**
 * Claude page mocks (docs/notes/2026-11-13-server-scan-area-api.md §12),
 * typed so a shape change fails `tsc`: server-scan's skill in its own
 * `GET /api/v1/skill` shape, as day1 passes it on, with server-scan's
 * address and the token line, and its zip. Never a live server-scan.
 */

import type { Page, Route } from "@playwright/test";
import { json } from "./api-handlers";
import { setUpServerScan } from "./server-scan";
import type { SkillAnswer } from "../../types/server-scan-skill";

export const SERVER_SCAN_URL = "https://server-scan.example";

const SKILL_MD = [
  "---",
  "name: server-scan-api",
  "---",
  "",
  "# Server Scan API",
  "",
  "## Connection - edit these two lines for your environment",
  "",
  "```",
  "BASE_URL=https://server-scan.example.internal",
  "AUDITOR_TOKEN=REPLACE_WITH_AUDITOR_TOKEN",
  "## not a heading",
  "```",
  "",
  "## Choose the endpoint",
  "",
  "### Filters",
  "",
  "`site_id`, `vendor`.",
].join("\n");

export function mockSkill(over: Partial<SkillAnswer> = {}): SkillAnswer {
  return {
    name: "server-scan-api",
    description: 'Queries the Server Scan REST API. Use whenever the user asks for servers ("all Dell servers in site1", "which servers are available").',
    when_to_use: "Also for questions about a server's BMC address.",
    allowed_tools: "Bash(curl *) Bash(jq *)",
    version: "0123456789ab",
    updated_at: "2026-11-01T08:00:00Z",
    files: [
      { path: "SKILL.md", content: SKILL_MD },
      { path: "references/endpoints.md", content: "# Endpoints\n\n## Servers\n\n`GET /api/v1/servers`" },
    ],
    server_scan_url: SERVER_SCAN_URL,
    token_line: "AUDITOR_TOKEN",
    ...over,
  };
}

/** A zip's first bytes are enough for the browser to save it; the bytes are not read. */
const ZIP = Buffer.from("PK\u0005\u0006" + "\u0000".repeat(18), "binary");

type Handler = (route: Route) => Promise<void> | void;

/**
 * Sign in as an admin with the area on, and mock the skill and its download.
 * Returns how many times each was asked for. Register a test's own routes
 * after this: mocks match LIFO.
 */
export async function setUpSkill(
  page: Page,
  { skill = mockSkill(), download }: { skill?: SkillAnswer | Handler; download?: Handler } = {}
): Promise<{ reads: () => number; downloads: () => number }> {
  let reads = 0;
  let downloads = 0;
  await setUpServerScan(page);
  await page.route("**/api/day1/server-scan/skill", (route) => {
    reads += 1;
    return typeof skill === "function" ? skill(route) : json(route, skill);
  });
  await page.route("**/api/day1/server-scan/skill/download", (route) => {
    downloads += 1;
    if (download) return download(route);
    return route.fulfill({
      status: 200,
      contentType: "application/zip",
      headers: { "content-disposition": 'attachment; filename="server-scan-api.zip"' },
      body: ZIP,
    });
  });
  return { reads: () => reads, downloads: () => downloads };
}
