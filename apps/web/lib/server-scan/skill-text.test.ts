import { describe, expect, it } from "vitest";
import { allowedTools, extractPrompts, outline } from "./skill-text";
import { mcpCommand, skillFolder, tokenPage, unzipCommand } from "./skill-setup";

// server-scan's own cases (frontend/src/features/skill/skillText.test.ts, McpSection.test.tsx at 92146d3)
describe("extractPrompts", () => {
  it("lifts the quoted examples out of the description", () => {
    const prompts = extractPrompts('Use for ("all Dell servers in tlv", "which servers are available").');
    expect(prompts).toEqual(["All Dell servers in tlv", "Which servers are available"]);
  });

  it("ignores short quotes and repeats", () => {
    expect(extractPrompts('say "ok" and "all Dell servers in tlv"', '"all Dell servers in tlv"')).toEqual([
      "All Dell servers in tlv",
    ]);
  });

  it("keeps at most six", () => {
    const quoted = Array.from({ length: 8 }, (_, i) => `"example question ${i}"`).join(" ");
    expect(extractPrompts(quoted)).toHaveLength(6);
  });
});

describe("outline", () => {
  it("lists ## and ### headings, skipping fenced code", () => {
    const headings = outline("# Title\n## One\n```\n## not a heading\n```\n### Two\n");
    expect(headings.map((h) => [h.level, h.text, h.line])).toEqual([
      [2, "One", 1],
      [3, "Two", 5],
    ]);
  });
});

describe("allowedTools", () => {
  it("splits the frontmatter's tools as server-scan does, keeping each tool's arguments", () => {
    expect(allowedTools("Bash(curl *) Bash(jq *)")).toEqual(["Bash(curl *)", "Bash(jq *)"]);
    expect(allowedTools("")).toEqual([]);
  });
});

describe("the setup's commands", () => {
  it("point the MCP command at server-scan and ask for a token", () => {
    expect(mcpCommand("https://scan.example/")).toBe(
      'claude mcp add --transport http server-scan https://scan.example/mcp --header "Authorization: Bearer <your token>"'
    );
  });

  it("unzip into the skills folder and send people to server-scan for their token", () => {
    expect(unzipCommand("server-scan-api")).toBe("unzip -o ~/Downloads/server-scan-api.zip -d ~/.claude/skills");
    expect(skillFolder("server-scan-api")).toBe("~/.claude/skills/server-scan-api");
    expect(tokenPage("https://scan.example")).toBe("https://scan.example/skill");
  });
});
