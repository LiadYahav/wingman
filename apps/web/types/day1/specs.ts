// ── Template schema (parsed from the Jinja2 AST by the backend) ─────────────

export interface TemplateField {
  name: string;
  type: "string" | "integer" | "boolean" | "list" | "object";
  required: boolean;
  default?: unknown;
  example?: string;
  fields?: TemplateField[]; // sub-fields for list-of-objects
}

// ── Cluster spec ────────────────────────────────────────────────────────────

/** A legacy declared variable; new specs leave the list empty. */
export interface SpecVariable {
  name: string;
  type: "string" | "integer" | "boolean" | "list" | "object";
  required?: boolean;
  default?: unknown;
  description?: string;
  pattern?: string | null;
  enum?: string[] | null;
  minimum?: number | null;
  maximum?: number | null;
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
      /**
       * Template-input paths whose value in `values` is fixed (§5, §6, ADR-0026):
       * `owner_anaf`, `nodepools[0].configs`, or the rule `nodepools[*].configs`
       * (§9, ADR-0029). Every other value in `values` is a preset.
       */
      locked_paths: string[];
      /** The shared cluster-template.j2, filled on read; never stored in the spec. */
      template: string;
      /** Template inputs: presets, and the locked values (`locked_paths`). */
      values?: Record<string, unknown>;
      /** One whole number per nodepool: they grow together, `ratio[i] * size` replicas (ADR-0040). */
      nodepool_ratio?: number[];
    };
    day2: {
      addons: SpecAddon[];
    };
  };
}

/** `GET /clusters/name-suggestion`: a free name for a new cluster from a flavor (ADR-0040). */
export interface NameSuggestion {
  /** `ocp4-<env>-<flavor>-<site>-<letter>`; `null` when there is none (`problems` says why). */
  name: string | null;
  env: string | null;
  short_name: string;
  sequence: string | null;
  problems: string[];
}

/** A spec as `GET /specs` lists it: a file that does not parse carries `load_error`. */
export interface SpecEntry extends ClusterSpec {
  load_error?: string | null;
  load_problems?: string[];
  /** Rules the stored flavor breaks: it loads, but saving it unchanged is refused (§5). */
  warnings?: string[];
  /** The `locked_paths` a create enforces (§5); a lock that breaks the rules is not in it. */
  enforced_locks?: string[];
}

/** `GET /specs/{name}`: one spec, with the commit its file was read at. */
export interface SpecDetail extends SpecEntry {
  /**
   * Send it back on update and delete (`?last_commit_id=`); a stale one is
   * 409 REVISION_CONFLICT (ADR-0006). Optional: a day1 service that predates
   * it does not send it, and a write then goes unguarded.
   */
  last_commit_id?: string | null;
}

/** A commit of `GET /specs/{name}/history`. */
export interface SpecCommit {
  sha: string;
  short_sha: string;
  message: string;
  author: string;
  date: string;
  web_url: string;
}
