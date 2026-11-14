/**
 * The Claude page's commands and addresses (ADR-0048's 3.27.0 amendment), in
 * server-scan's words (its `SkillPage.tsx` and `McpSection.tsx` at 92146d3).
 * They name server-scan, never Wingman: Claude Code calls server-scan's API
 * itself, with the person's own token, which server-scan makes on its own
 * Claude page (`/skill`) for someone signed in to it.
 */

/** The placeholder the MCP command carries until the person pastes their token over it. */
export const TOKEN_PLACEHOLDER = "<your token>";

/** Where the skill unzips to: `~/.claude/skills/<name>`. */
export const skillFolder = (name: string) => `~/.claude/skills/${name}`;

/** Step 2: unzip the download into the skills folder. */
export const unzipCommand = (name: string) => `unzip -o ~/Downloads/${name}.zip -d ~/.claude/skills`;

/** server-scan's address without a trailing slash, so paths join cleanly. */
const base = (serverScanUrl: string) => serverScanUrl.replace(/\/+$/, "");

/** The one command that connects Claude Code to server-scan's MCP endpoint (its ADR-0054). */
export const mcpCommand = (serverScanUrl: string) =>
  `claude mcp add --transport http server-scan ${base(serverScanUrl)}/mcp --header "Authorization: Bearer ${TOKEN_PLACEHOLDER}"`;

/** server-scan's own Claude page, where a person signed in to it makes their token. */
export const tokenPage = (serverScanUrl: string) => `${base(serverScanUrl)}/skill`;
