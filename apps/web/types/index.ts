export * from "./day2";

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface UserInfo {
  username: string;
  groups: string[];
  uid: string;
  full_name?: string;
  role: "admin" | "viewer";
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
  /** day1 only: the platform workflow that opened it; it is reviewed and merged in GitLab, not here. */
  opened_by_workflow?: "provision-cluster" | null;
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
export * from "./quick-links";
export * from "./upgrade";
