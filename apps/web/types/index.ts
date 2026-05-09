// ── Auth ──────────────────────────────────────────────────────────────────────

export interface UserInfo {
  username: string;
  groups: string[];
  uid: string;
  full_name?: string;
  role: "admin" | "viewer";
}

// ── Template Schema (dynamic, parsed from Jinja2 AST by the backend) ─────────

export interface TemplateField {
  name: string;
  type: "string" | "integer" | "boolean" | "list" | "object";
  required: boolean;
  default?: unknown;
  example?: string;
  fields?: TemplateField[];  // sub-fields for list-of-objects
}

// ── Cluster Spec ──────────────────────────────────────────────────────────────

export interface SpecVariable {
  name: string;
  type: "string" | "integer" | "boolean" | "list" | "object";
  required?: boolean;
  default?: unknown;
  description?: string;
  pattern?: string;
  enum?: string[];
  minimum?: number;
  maximum?: number;
}

export interface OverrideableField {
  path: string;
  type: "string" | "integer" | "boolean" | "object" | "array";
  default?: unknown;
  description?: string;
}

export interface SpecAddon {
  team: string;
  name: string;
  version: string;
  overrideable: OverrideableField[];
}

export interface ClusterSpec {
  apiVersion: string;
  kind: string;
  metadata: {
    name: string;
    description?: string;
    version: string;
    labels?: Record<string, string>;
  };
  spec: {
    day1: {
      variables: SpecVariable[];
      structure: Record<string, unknown>;
      immutable_paths: string[];
      template: string;
    };
    day2: {
      addons: SpecAddon[];
    };
  };
}

// ── Cluster ───────────────────────────────────────────────────────────────────

export interface ClusterStatus {
  name: string;
  site: string;
  mce: string;
  phase: "Provisioning" | "Ready" | "Error" | "Deleting" | "Unknown";
  spec_name?: string;
  spec_version?: string;
  created_by?: string;
  created_at?: string;
  is_drifted: boolean;
}

export interface NodePoolStatus {
  name: string;
  ready_replicas: number;
  desired_replicas: number;
  problems: string[];
}

export interface ClusterLiveStatus {
  cluster_name: string;
  hc_problems: string[];
  node_pools: NodePoolStatus[];
  error?: string;
}

export interface ClusterMetadata {
  specName: string;
  specVersion: string;
  createdBy: string;
  createdAt: string;
  site: string;
  mce: string;
  variables: Record<string, unknown>;
  immutablePaths?: string[];
  addonOverrides?: Record<string, Record<string, unknown>>;
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

// ── MR / Approval ─────────────────────────────────────────────────────────────

export interface MRAuthor {
  username: string;
  name: string;
  avatar_url: string;
}

export interface MRDetail {
  iid: number;
  title: string;
  description: string;
  author: MRAuthor;
  state: "opened" | "merged" | "closed";
  created_at: string;
  updated_at: string;
  web_url: string;
  source_branch: string;
  target_branch: string;
  labels: string[];
  repo: "day1" | "day2" | "specs"; // added by frontend aggregation
}

export interface FileDiff {
  old_path: string;
  new_path: string;
  diff: string;
  new_file: boolean;
  renamed_file: boolean;
  deleted_file: boolean;
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
}
