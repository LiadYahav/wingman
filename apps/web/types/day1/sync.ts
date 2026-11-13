import type { AddonDrift, NodepoolRef, ValueDrift, VersionDifference } from "./drift";

// ── Sync a cluster to its flavor (§12, ADR-0037) ────────────────────────────

/** A person's network hardware choice for a nodepool whose own can't be read. */
export interface HardwareChoice {
  nodepool: number;
  hardware: string;
}

/** `POST /clusters/{name}/sync/preview` body. */
export interface SyncPreviewRequest {
  hardware?: HardwareChoice[];
}

/** A config the sync removes; each must be confirmed. */
export interface ConfigRemoval {
  nodepool: NodepoolRef;
  name: string;
}

/** A nodepool whose configs change: merging rolls its nodes. */
export interface Rebooting {
  nodepool: NodepoolRef;
  replicas: number | null;
  /** `null` when unset: the chart's `InPlace` (drain and reboot). */
  upgrade_type: string | null;
  /** `inPlace.maxUnavailable`; `null`: one node at a time. */
  max_unavailable: number | string | null;
  /** `upgradeType: Replace`: new nodes are provisioned and the old ones removed. */
  replaces_nodes: boolean;
}

/** `POST /clusters/{name}/sync/preview`. */
export interface SyncPreview {
  cluster: string;
  site: string;
  mce: string;
  path: string;
  /** Send it back with the sync. */
  last_commit_id: string;
  spec_name: string;
  /** The flavor's current version; send it back with the sync. */
  spec_version: string;
  /** The version the file's header names now. */
  file_spec_version: string | null;
  /** Every locked value the file does not hold, with the hardware choices applied. */
  changes: ValueDrift[];
  /** The cluster file change as a unified diff; empty when nothing changes. */
  diff: string;
  removals: ConfigRemoval[];
  rebooting: Rebooting[];
  /** Why the sync can't run now; `can_sync` is then false. */
  problems: string[];
  /** Worth checking before merging; they don't block. */
  warnings: string[];
  can_sync: boolean;
  /** Not in the day1 MR: install them through day2 (one MR per team). */
  addons_to_install: AddonDrift[];
  version_differences: VersionDifference[];
  /** Set when day2 did not answer: missing add-ons are unknown. */
  addons_error: string | null;
}

/** `POST /clusters/{name}/sync` body: what the preview showed, the removals confirmed. */
export interface SyncRequest {
  last_commit_id: string;
  spec_version: string;
  hardware?: HardwareChoice[];
  /** Exactly the preview's `removals`, or the sync is refused. */
  confirm_removals: { nodepool: number; name: string }[];
}
