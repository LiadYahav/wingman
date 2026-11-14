/**
 * The Claude page's answer (docs/notes/2026-11-13-server-scan-area-api.md §12):
 * server-scan's `GET /api/v1/skill` in its own shape (its `frontend/src/api/skill.ts`,
 * team-redbull/server-scan at 92146d3), plus where server-scan is for people
 * and the token line Wingman's copy of the zip names.
 */

/** One file of the skill: `SKILL.md`, then the references. */
export interface SkillFile {
  path: string;
  content: string;
}

/** server-scan's skill as it holds it now; `version` changes whenever a file does. */
export interface Skill {
  name: string;
  description: string;
  when_to_use: string;
  allowed_tools: string;
  version: string;
  updated_at: string;
  files: SkillFile[];
}

/** `GET /api/day1/server-scan/skill`. */
export interface SkillAnswer extends Skill {
  /** server-scan's address for people: written into the zip, the MCP command's and the token page's. */
  server_scan_url: string;
  /** The placeholder the zip's `SKILL.md` names: `VIEWER_TOKEN` or `AUDITOR_TOKEN`. */
  token_line: string;
}
