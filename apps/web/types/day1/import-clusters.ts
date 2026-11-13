import type { MRDetail } from "../index";
import type { ErrorCode } from "../problem";
import type { ClusterDrift } from "./drift";

// ── Import existing clusters into a flavor (§11, ADR-0037) ──────────────────

/** A cluster to compare with a flavor; `site` and `mce` only when the name is ambiguous. */
export interface ClusterPick {
  name: string;
  site?: string | null;
  mce?: string | null;
}

/** `POST /specs/{name}/import/preview` body (up to 500 clusters). */
export interface ImportPreviewRequest {
  clusters: ClusterPick[];
}

/** `ready`: no flavor yet; `relink`: follows another; `linked`: follows this one; `refused`: can't be edited. */
export type ImportStatus = "ready" | "relink" | "linked" | "refused";

export interface ImportCandidate {
  name: string;
  site: string;
  mce: string;
  path: string;
  /** Send it back with the import. */
  last_commit_id: string;
  status: ImportStatus;
  /** The flavor the file follows now. */
  linked_spec: { name: string; version: string | null } | null;
  /** Why it cannot be imported as it is (empty for `ready`). */
  problems: string[];
  /** The cluster against this flavor: what will show as drift once it is linked. */
  drift: ClusterDrift;
}

/** `POST /specs/{name}/import/preview`. */
export interface ImportPreview {
  spec_name: string;
  /** Send it back with the import. */
  spec_version: string;
  /** About the flavor: positional nodepool locks compare whichever nodepool is there. */
  warnings: string[];
  clusters: ImportCandidate[];
}

/** One cluster of `POST /specs/{name}/import`, as the preview returned it. */
export interface ImportPick {
  name: string;
  site: string;
  mce: string;
  last_commit_id: string;
  /** `true` to move a cluster that follows another flavor to this one. */
  relink?: boolean;
}

/** `POST /specs/{name}/import` body: at most 50 clusters, one day1 MR each (ADR-0044). */
export interface ImportRequest {
  spec_version: string;
  clusters: ImportPick[];
}

/** A picked cluster and the day1 MR that links it to the flavor. */
export interface ImportedCluster {
  name: string;
  site: string;
  mce: string;
  path: string;
  merge_request: MRDetail;
}

/** A picked cluster, checked like the others, whose MR did not open. */
export interface ImportFailure {
  name: string;
  site: string;
  mce: string;
  path: string;
  /**
   * The problem code its write failed with. `AMBIGUOUS_WRITE`: GitLab did not
   * confirm it, so the MR may exist (check before importing it again);
   * `GIT_UNAVAILABLE`: nothing was sent; `REVISION_CONFLICT`: the file moved
   * since the preview.
   */
  code: ErrorCode | (string & {});
  detail: string;
}

/**
 * `POST /specs/{name}/import` (201): one day1 MR per cluster, each list in
 * pick order (docs/notes/2026-11-12-import-mr-per-cluster.md). When none
 * opened, the answer is the failure's problem instead.
 */
export interface ImportResult {
  spec_name: string;
  spec_version: string;
  merge_requests: ImportedCluster[];
  failed: ImportFailure[];
}
