import type { Finding } from "./destinations";

// ── Writes (ADR-0022) ────────────────────────────────────────────────────────

export interface InstallBody {
  override_values: Record<string, unknown>;
  /** Honoured only if equal to the inherited revision, or with `emergency_pin`. */
  version?: string;
  emergency_pin?: boolean;
  /** Needed only when no layer has a lowercase repourl. */
  repourl?: string;
  project_namespace?: string;
  message?: string;
}

export interface UpdateBody {
  override_values: Record<string, unknown>;
  version?: string;
  emergency_pin?: boolean;
  last_commit_id?: string | null;
  message?: string;
}

export interface BulkItem {
  team: string;
  addon: string;
  version?: string;
  emergency_pin?: boolean;
  override_values: Record<string, unknown>;
}

export interface BulkBody {
  addons: BulkItem[];
  custom_message?: string;
}

export interface MergePreviewBody {
  team: string;
  addon: string;
  cluster: string;
  mce?: string;
  version?: string;
  override_values?: Record<string, unknown>;
  /** The stack layer `override_values` replaces (a fleet default's `values-<env>.yaml`); the cluster's own file when absent. */
  override_path?: string;
}

/** A day2 merge request (`MRDetailOut`). */
export interface Day2MergeRequest {
  iid: number;
  title: string;
  description: string;
  author: { username: string; name: string; avatar_url: string | null };
  state: string;
  created_at: string;
  updated_at: string;
  web_url: string;
  source_branch: string;
  target_branch: string;
  labels: string[];
  repo: "day2";
  has_conflicts: boolean | null;
  team: string;
  project_id: number;
  /** The MR head: what an approver reviews. */
  sha: string;
  gitlab_author: string;
}

export interface FileChange {
  action: "create" | "update" | "delete" | "move" | (string & {});
  path: string;
}

/** An opened MR plus what it writes and what to expect after the merge. */
export interface ChangeResult extends Day2MergeRequest {
  cluster: string;
  files: FileChange[];
  app_names: string[];
  warnings: Finding[];
  /** Read these: what else the change registers, sync, and that a removal orphans. */
  notes: string[];
}

/** `POST /api/day2/clusters/{id}/addons/bulk`: one MR per team. */
export interface BulkResult {
  merge_requests: ChangeResult[];
  failed: { team: string; error: string; detail: string }[];
}

/** `GET /api/day2/clusters/{id}/upgrade-check?to=`. */
export interface UpgradeCheck {
  cluster: string;
  from_version: string | null;
  to_version: string;
  warnings: Finding[];
}
