// ── Teams and their write access (ADR-0043) ───────────────────────────────────

/** GitLab's role names, lowest first; `none` is no membership at all. */
export type AccessRole =
  | "none"
  | "minimal"
  | "guest"
  | "planner"
  | "reporter"
  | "developer"
  | "maintainer"
  | "owner"
  /** Wingman could not read the account's access to the project: the team is read-only (ADR-0053). */
  | "unknown"
  | (string & {});

/**
 * `GET /api/day2/teams`, `GET /api/day2/teams/{team}`: a team, its project,
 * and whether Wingman's GitLab account may write there (Developer or higher on
 * the project). A read-only team's writes are refused with `TEAM_READ_ONLY`.
 */
export interface Team {
  name: string;
  project_id: number;
  path_with_namespace: string;
  web_url: string;
  writable: boolean;
  /** GitLab's number: 0 none … 20 reporter, 30 developer, 40 maintainer, 50 owner. */
  access_level: number;
  access_role: AccessRole;
  /** One sentence to show as is; `null` when `writable`. */
  read_only_reason: string | null;
}
