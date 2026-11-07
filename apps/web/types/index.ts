export * from "./day2";

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface UserInfo {
  username: string;
  groups: string[];
  uid: string;
  full_name?: string;
  role: "admin" | "viewer";
}

// ── Addon ─────────────────────────────────────────────────────────────────────

export interface YamlParseError {
  message: string;
  line: number | null;
  column: number | null;
  context: string | null; // The problematic line
  snippet: string | null; // Multi-line snippet with error highlighted
}

export interface AddonArgoMetadata {
  projectNamespace: string;
  repourl: string;
  targetRevision: string;
  syncPolicy: Record<string, unknown>;
}

export interface AddonCatalogEntry {
  team: string;
  name: string;
  available_versions: string[];
  current_version: string;
  default_values: Record<string, unknown>;
  argocd_metadata?: AddonArgoMetadata;
  dependencies: string[];
}

export interface SpecCommit {
  sha: string;
  short_sha: string;
  message: string;
  author: string;
  date: string;
  web_url: string;
}

export interface InstalledAddon {
  team: string;
  name: string;
  version: string;
  override_values: Record<string, unknown>;
  available_versions?: string[];
  parse_errors?: YamlParseError[];
  gitlab_url?: string;
}

export interface MergedAddonValues {
  merged: Record<string, unknown>;
  provenance: Record<string, unknown>; // same structure, values: "chart"|"team"|"cluster"
  chart_values: Record<string, unknown>;
  team_values: Record<string, unknown>;
  cluster_values: Record<string, unknown>;
  addon_name: string;
  team: string;
  version: string;
}

// ── MR / Approval (both services) ─────────────────────────────────────────────

export interface MRAuthor {
  /** The requester from the MR footer, not the service account. */
  username: string;
  name: string;
  avatar_url: string | null;
}

export interface MRDetail {
  iid: number;
  project_id: number;
  title: string;
  description: string;
  author: MRAuthor;
  state: "opened" | "merged" | "closed" | "locked";
  created_at: string;
  updated_at: string;
  /** day1 only. */
  merged_at?: string | null;
  web_url: string;
  source_branch: string;
  target_branch: string;
  labels: string[];
  repo: "day1" | "day2" | "specs";
  has_conflicts: boolean | null;
  /** The source branch head: an approval names the one the reviewer saw. */
  sha: string;
  /** day2 only: the team repo; day2 MRs are addressed by team and iid. */
  team?: string;
  /** day2 only: GitLab's author (the service account). */
  gitlab_author?: string;
}

export interface FileDiff {
  old_path: string;
  new_path: string;
  diff: string;
  new_file: boolean;
  renamed_file: boolean;
  deleted_file: boolean;
}

/** `GET /approvals/...`: an MR and its diff. */
export interface ApprovalDetail {
  mr: MRDetail;
  diffs: FileDiff[];
}

export interface UpdateMRFile {
  path: string;
  content: string;
}

// ── Audit ─────────────────────────────────────────────────────────────────────

export interface CommitRecord {
  id: string;
  short_id: string;
  title: string;
  author_name: string;
  author_email: string;
  authored_date: string;
  message: string;
  web_url: string;
  repo: "day1" | "day2" | "specs";
  /** day2 only: the team repo the commit is in. */
  team?: string;
}

export * from "./problem";
export * from "./day1";
