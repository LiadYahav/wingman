/**
 * The flavor editor's model: the draft a person edits, the document a save
 * sends, day1's checks mirrored for instant feedback, where day1's problems
 * belong, and the cluster-file preview request. The contract is
 * docs/notes/2026-11-08-flavors-v2-api-changes.md (§2-§6, §9); the decisions
 * are ADR-0026 (a lock is a fixed value), ADR-0027 (machine configs and the
 * nodepool defaults), ADR-0028 (owners are numbers) and ADR-0029 (the configs
 * rule). Day1 is the authority: these checks only answer sooner.
 *
 * Every value lives in `spec.day1.values` (presets and locked values alike);
 * a path in `locked_paths` makes its value fixed. The draft keeps `values`
 * as loaded and changes only what the person edits, so keys the editor does
 * not show survive a save.
 */

import {
  NETWORK_CONFIG,
  asEntries,
  cleanEntry,
  entryProblems,
  isNetworkEntry,
  withHardware,
} from "@/lib/machine-configs";
import { specDocument } from "@/lib/specs";
import { isMapping, sameValues, type Values } from "@/lib/values";
import type {
  ClusterSpec,
  ConfigEntry,
  CreateClusterRequest,
  MachineConfigs,
  Mce,
  SpecAddon,
  TemplateField,
} from "@/types";

// ── What can be locked (§6, §9) ─────────────────────────────────────────────

export const OWNERS = [
  { path: "owner_merkaz", label: "Merkaz" },
  { path: "owner_anaf", label: "Anaf" },
  { path: "owner_mador", label: "Mador" },
] as const;

export const PLATFORM = "platform";
/** The one rule: every nodepool has exactly these configs (ADR-0029). */
export const CONFIGS_RULE = "nodepools[*].configs";

export type NodepoolKey = "replicas" | "configs" | "node_labels";
const NODEPOOL_LOCKABLE: readonly NodepoolKey[] = ["replicas", "configs", "node_labels"];
const TOP_LOCKABLE: readonly string[] = [...OWNERS.map((o) => o.path), PLATFORM];
const POSITIONAL = /^nodepools\[(0|[1-9]\d{0,2})\]\.(replicas|configs|node_labels)$/;
const POSITIONAL_CONFIGS = /^nodepools\[(0|[1-9]\d{0,2})\]\.configs$/;

/** The inputs day1 sets for each cluster at create: never preset or locked here. */
const PER_CLUSTER = new Set(["cluster_name", "site", "site_name", "mce", "mce_name", "openshift_release_version"]);
/** Top-level inputs the editor shows in their own places. */
const MODELED_TOP = new Set([...TOP_LOCKABLE, "nodepools"]);

export const nodepoolPath = (index: number, key: string) => `nodepools[${index}].${key}`;

function isLockable(path: string): boolean {
  return TOP_LOCKABLE.includes(path) || POSITIONAL.test(path) || path === CONFIGS_RULE;
}

// ── The draft ───────────────────────────────────────────────────────────────

export interface FlavorDraft {
  name: string;
  version: string;
  description: string;
  /** `spec.day1.values`: presets and locked values. */
  values: Values;
  /** `spec.day1.locked_paths`, in the order they were added. */
  locked: string[];
  /** `spec.day1.structure`; `nodepools` holds one placeholder per nodepool. */
  structure: Values;
  addons: SpecAddon[];
  /** One stable key per nodepool, for the page only (never saved). */
  keys: number[];
  /** `spec.day1.nodepool_ratio` as typed, one per nodepool; empty: no ratio (ADR-0040). */
  ratio: string[];
}

export type ConfigsMode = "each" | "rule";

const clone = <T,>(value: T): T => (value === undefined ? value : (JSON.parse(JSON.stringify(value)) as T));

function poolList(values: Values): Values[] {
  return Array.isArray(values.nodepools) ? values.nodepools.map((p) => (isMapping(p) ? p : {})) : [];
}

/** A new flavor: one nodepool, its configs prefilled from the nodepool defaults. */
export function newDraft(defaults: ConfigEntry[]): FlavorDraft {
  return {
    name: "",
    version: "1.0.0",
    description: "",
    values: defaults.length > 0 ? { nodepools: [{ configs: defaults.map(cleanEntry) }] } : {},
    locked: [],
    structure: { nodepools: [{}] },
    addons: [],
    keys: [0],
    ratio: [],
  };
}

/**
 * A loaded flavor as a draft. Owners stored as numbers become their digits
 * (day1 refuses a number, §4); a values list longer than the structure's
 * gets placeholders, so every nodepool the flavor sets shows.
 */
export function draftFromSpec(spec: ClusterSpec): FlavorDraft {
  const day1 = spec.spec.day1;
  const values = clone(day1.values ?? {});
  for (const { path } of OWNERS) {
    if (typeof values[path] === "number") values[path] = String(values[path]);
  }
  const structure = clone(day1.structure ?? {});
  const placeholders = Array.isArray(structure.nodepools) ? structure.nodepools : null;
  const valueCount = poolList(values).length;
  if (valueCount > (placeholders?.length ?? 0)) {
    structure.nodepools = [...(placeholders ?? []), ...Array.from({ length: valueCount - (placeholders?.length ?? 0) }, () => ({}))];
  }
  return {
    name: spec.metadata.name,
    version: spec.metadata.version,
    description: spec.metadata.description ?? "",
    values,
    locked: [...(day1.locked_paths ?? [])],
    structure,
    addons: clone(spec.spec.day2.addons ?? []),
    keys: Array.from({ length: Array.isArray(structure.nodepools) ? structure.nodepools.length : 0 }, (_, i) => i),
    ratio: (day1.nodepool_ratio ?? []).map(String),
  };
}

// ── The nodepool ratio (ADR-0040) ───────────────────────────────────────────

const RATIO_HINT = "A whole number from 1 to 100";

/**
 * Turn the ratio on (every nodepool at 1) or off. On, the first nodepool's
 * replicas, if set, become the size every nodepool follows.
 */
export function setRatioOn(draft: FlavorDraft, on: boolean): FlavorDraft {
  if (!on) return { ...draft, ratio: [] };
  const next = { ...draft, ratio: Array.from({ length: nodepoolCount(draft) }, () => "1") };
  const first = nodepoolValues(draft, 0).replicas;
  return isWholeNumber(first) && Number(first) >= 1 ? withRatioSize(next, Number(first)) : next;
}

/** One nodepool's part of the ratio; the replicas follow it at the size they had. */
export function setPoolRatio(draft: FlavorDraft, index: number, value: string): FlavorDraft {
  const size = ratioSize(draft);
  const next = { ...draft, ratio: draft.ratio.map((r, i) => (i === index ? value : r)) };
  return size !== null ? withRatioSize(next, size) : next;
}

/** The ratio's parts as numbers; `null` while one is not a whole number from 1 to 100. */
function ratioParts(draft: FlavorDraft): number[] | null {
  const parts = draft.ratio.map((r) => (/^\d+$/.test(r.trim()) ? Number(r) : NaN));
  return parts.length > 0 && parts.every((n) => n >= 1 && n <= 100) ? parts : null;
}

/**
 * The size the nodepools' replicas are at: the first nodepool with replicas,
 * divided by its part. `null` with no ratio, no replicas, or replicas that
 * are not a whole multiple of their part.
 */
export function ratioSize(draft: FlavorDraft): number | null {
  const parts = ratioParts(draft);
  if (!parts) return null;
  for (let i = 0; i < parts.length; i++) {
    const replicas = nodepoolValues(draft, i).replicas;
    if (replicas === undefined || replicas === "") continue;
    if (!isWholeNumber(replicas)) return null;
    const size = Number(replicas) / parts[i];
    return Number.isInteger(size) && size >= 1 ? size : null;
  }
  return null;
}

/** Every sized nodepool's replicas at its part times `size`. */
function withRatioSize(draft: FlavorDraft, size: number): FlavorDraft {
  const parts = ratioParts(draft);
  if (!parts) return draft;
  return parts.reduce((d, part, i) => setNodepoolValue(d, i, "replicas", part * size), draft);
}

/**
 * One nodepool's replicas under a ratio: the others follow (ADR-0040). At
 * 1:2:1, 3 on the first gives 3 · 6 · 3, and 4 on the second 2 · 4 · 2.
 * Cleared, every sized nodepool is cleared. A number that is not a whole
 * multiple of this nodepool's part stays as typed, for the check to flag.
 */
export function setSizedReplicas(draft: FlavorDraft, index: number, value: number | string | undefined): FlavorDraft {
  const parts = ratioParts(draft);
  if (!parts || index >= parts.length) return setNodepoolValue(draft, index, "replicas", value);
  if (value === undefined) return parts.reduce((d, _, i) => setNodepoolValue(d, i, "replicas", undefined), draft);
  const size = typeof value === "number" ? value / parts[index] : NaN;
  if (Number.isInteger(size) && size >= 1) return withRatioSize(draft, size);
  return setNodepoolValue(draft, index, "replicas", value);
}

/** `1:2:1`; a part that is not a number yet shows as `?`. */
export function ratioLabel(draft: FlavorDraft): string {
  return draft.ratio.map((r) => (/^\d+$/.test(r.trim()) ? String(Number(r)) : "?")).join(":");
}

function ratioValue(text: string): number | string {
  return /^\d+$/.test(text.trim()) ? Number(text) : text;
}

export function nodepoolCount(draft: FlavorDraft): number {
  return Array.isArray(draft.structure.nodepools) ? draft.structure.nodepools.length : 0;
}

export function nodepoolValues(draft: FlavorDraft, index: number): Values {
  return poolList(draft.values)[index] ?? {};
}

export function configsMode(draft: FlavorDraft): ConfigsMode {
  return draft.locked.includes(CONFIGS_RULE) ? "rule" : "each";
}

export const isLocked = (draft: FlavorDraft, path: string) => draft.locked.includes(path);

/** `values.nodepools` as `count` mappings, or gone when none of them sets anything. */
function normalizePools(values: Values, count: number): Values {
  if (!Array.isArray(values.nodepools)) return values;
  const list = poolList(values);
  const pools = Array.from({ length: count }, (_, i) => list[i] ?? {});
  if (pools.every((p) => Object.keys(p).length === 0)) {
    const rest = { ...values };
    delete rest.nodepools;
    return rest;
  }
  return { ...values, nodepools: pools };
}

export function setTopValue(draft: FlavorDraft, key: string, value: unknown): FlavorDraft {
  const values = { ...draft.values };
  if (value === undefined) delete values[key];
  else values[key] = value;
  return { ...draft, values };
}

export function setNodepoolValue(draft: FlavorDraft, index: number, key: string, value: unknown): FlavorDraft {
  const count = nodepoolCount(draft);
  const list = poolList(draft.values);
  const pools = Array.from({ length: count }, (_, i) => ({ ...(list[i] ?? {}) }));
  if (value === undefined) delete pools[index][key];
  else pools[index][key] = value;
  return { ...draft, values: normalizePools({ ...draft.values, nodepools: pools }, count) };
}

/** Lock or unlock `path`. A locked list or map with nothing in it is locked empty, which is a value. */
export function setLocked(draft: FlavorDraft, path: string, locked: boolean): FlavorDraft {
  const has = draft.locked.includes(path);
  if (locked === has) return draft;
  let next: FlavorDraft = { ...draft, locked: locked ? [...draft.locked, path] : draft.locked.filter((p) => p !== path) };
  const match = /^nodepools\[(\d+)\]\.(configs|node_labels)$/.exec(path);
  if (match) {
    const index = Number(match[1]);
    const key = match[2];
    const current = nodepoolValues(next, index)[key];
    const empty = key === "configs" ? [] : {};
    if (locked && current === undefined) next = setNodepoolValue(next, index, key, empty);
    if (!locked && sameValues(current, empty)) next = setNodepoolValue(next, index, key, undefined);
  }
  return next;
}

export function removeLock(draft: FlavorDraft, path: string): FlavorDraft {
  return { ...draft, locked: draft.locked.filter((p) => p !== path) };
}

// ── Machine configs (ADR-0027, ADR-0029) ────────────────────────────────────

/** The hardware of a list's network entry, if it has one. */
export function hardwareOf(entries: ConfigEntry[]): string | null {
  return entries.find(isNetworkEntry)?.hardware ?? null;
}

export function poolConfigs(draft: FlavorDraft, index: number): ConfigEntry[] {
  return asEntries(nodepoolValues(draft, index).configs);
}

/** The rule's list: the first nodepool's configs, with `nm-conf` left to each nodepool. */
export function ruleEntries(draft: FlavorDraft): ConfigEntry[] {
  return poolConfigs(draft, 0).map((e) => (isNetworkEntry(e) ? { name: NETWORK_CONFIG, hardware: null } : { name: e.name }));
}

/** Every nodepool gets `shared`, each keeping its own network hardware. */
export function setRuleEntries(draft: FlavorDraft, shared: ConfigEntry[]): FlavorDraft {
  let next = draft;
  for (let i = 0; i < nodepoolCount(draft); i++) {
    const hardware = hardwareOf(poolConfigs(draft, i));
    const configs = shared.map((e) => (isNetworkEntry(e) ? { name: NETWORK_CONFIG, hardware } : { name: e.name }));
    next = setNodepoolValue(next, i, "configs", configs);
  }
  return next;
}

/** Under the rule, one nodepool's network hardware (a preset, ADR-0029). */
export function setPoolHardware(draft: FlavorDraft, index: number, hardware: string | null): FlavorDraft {
  const configs = poolConfigs(draft, index).map((e) => (isNetworkEntry(e) ? { name: NETWORK_CONFIG, hardware } : e));
  return setNodepoolValue(draft, index, "configs", configs);
}

/**
 * Switch between configs per nodepool and the rule. The rule starts from the
 * first nodepool's configs (or the defaults), lists `nm-conf` once, and
 * replaces any positional configs lock; leaving it keeps each nodepool's
 * configs as its own preset.
 */
export function setConfigsMode(
  draft: FlavorDraft,
  mode: ConfigsMode,
  defaults: ConfigEntry[],
  hardware: string | null = hardwareOf(defaults)
): FlavorDraft {
  if (configsMode(draft) === mode) return draft;
  if (mode === "each") return removeLock(draft, CONFIGS_RULE);
  let next = nodepoolCount(draft) === 0 ? addNodepool(draft, defaults, hardware) : draft;
  const first = poolConfigs(next, 0);
  const base = first.length > 0 ? first : defaults;
  const statics = base.filter((e) => !isNetworkEntry(e)).map((e) => ({ name: e.name }));
  const shared: ConfigEntry[] = [{ name: NETWORK_CONFIG, hardware: null }, ...statics];
  next = { ...next, locked: [...next.locked.filter((p) => !POSITIONAL_CONFIGS.test(p)), CONFIGS_RULE] };
  next = setRuleEntries(next, shared);
  // A nodepool with no network hardware yet starts at the default (generic, when mc-files/ has it)
  if (hardware) {
    for (let i = 0; i < nodepoolCount(next); i++) {
      if (!hardwareOf(poolConfigs(next, i))) next = setPoolHardware(next, i, hardware);
    }
  }
  return next;
}

// ── Nodepools ───────────────────────────────────────────────────────────────

/**
 * A new nodepool: the rule's configs under the rule (its network hardware at
 * `hardware`, the default), else a copy of the defaults.
 */
export function addNodepool(
  draft: FlavorDraft,
  defaults: ConfigEntry[],
  hardware: string | null = hardwareOf(defaults)
): FlavorDraft {
  const index = nodepoolCount(draft);
  const placeholders = Array.isArray(draft.structure.nodepools) ? draft.structure.nodepools : [];
  let next: FlavorDraft = {
    ...draft,
    structure: { ...draft.structure, nodepools: [...placeholders, {}] },
    keys: [...draft.keys, Math.max(-1, ...draft.keys) + 1],
  };
  const configs = configsMode(draft) === "rule" ? withHardware(ruleEntries(draft), hardware) : defaults.map(cleanEntry);
  if (configs.length > 0) next = setNodepoolValue(next, index, "configs", configs);
  if (draft.ratio.length > 0) {
    const size = ratioSize(draft);
    next = { ...next, ratio: [...draft.ratio, "1"] };
    if (size !== null) next = withRatioSize(next, size);
  }
  return next;
}

/** Remove one nodepool; locks on later positions move down with their nodepool. */
export function removeNodepool(draft: FlavorDraft, index: number): FlavorDraft {
  const placeholders = Array.isArray(draft.structure.nodepools) ? draft.structure.nodepools : [];
  const count = Math.max(0, placeholders.length - 1);
  let values = draft.values;
  if (Array.isArray(values.nodepools)) {
    values = normalizePools({ ...values, nodepools: poolList(values).filter((_, i) => i !== index) }, count);
  }
  const locked = draft.locked.flatMap((path) => {
    const match = /^nodepools\[(\d+)\](\..*)$/.exec(path);
    if (!match) return [path];
    const at = Number(match[1]);
    if (at === index) return [];
    return [at > index ? `nodepools[${at - 1}]${match[2]}` : path];
  });
  return {
    ...draft,
    values,
    locked,
    structure: { ...draft.structure, nodepools: placeholders.filter((_, i) => i !== index) },
    keys: draft.keys.filter((_, i) => i !== index),
    ratio: draft.ratio.length > 0 && count > 0 ? draft.ratio.filter((_, i) => i !== index) : [],
  };
}

// ── Other template inputs (presets only) ────────────────────────────────────

export interface OtherInput {
  name: string;
  type: TemplateField["type"];
  example?: string;
  /** Not in the template's inputs: a value the flavor keeps, which the template does not read. */
  unread: boolean;
}

/** Top-level inputs besides owners, platform and nodepools: the schema's, and any the flavor sets. */
export function otherTopInputs(schema: TemplateField[], values: Values): OtherInput[] {
  const fromSchema = schema
    .filter((f) => !MODELED_TOP.has(f.name) && !PER_CLUSTER.has(f.name))
    .map((f) => ({ name: f.name, type: f.type, example: f.example, unread: false }));
  const known = new Set(schema.map((f) => f.name));
  const extra = Object.keys(values)
    .filter((k) => !MODELED_TOP.has(k) && !known.has(k) && !["cluster_name", "site", "site_name", "mce", "mce_name"].includes(k))
    .map((k) => ({ name: k, type: typeOf(values[k]), unread: k !== "openshift_release_version" }));
  const release = values.openshift_release_version !== undefined && known.has("openshift_release_version")
    ? [{ name: "openshift_release_version", type: "string" as const, unread: false }]
    : [];
  return [...fromSchema, ...release, ...extra];
}

/** A nodepool's inputs besides replicas, configs and node labels. */
export function otherPoolInputs(schema: TemplateField[], pool: Values): OtherInput[] {
  const fields = schema.find((f) => f.name === "nodepools")?.fields ?? [];
  const lockable = new Set<string>(NODEPOOL_LOCKABLE);
  const fromSchema = fields
    .filter((f) => !lockable.has(f.name))
    .map((f) => ({ name: f.name, type: f.type, example: f.example, unread: false }));
  const known = new Set(fields.map((f) => f.name));
  const extra = Object.keys(pool)
    .filter((k) => !lockable.has(k) && !known.has(k))
    .map((k) => ({ name: k, type: typeOf(pool[k]), unread: fields.length > 0 }));
  return [...fromSchema, ...extra];
}

function typeOf(value: unknown): TemplateField["type"] {
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return "integer";
  if (Array.isArray(value)) return "list";
  if (isMapping(value)) return "object";
  return "string";
}

// ── The document ────────────────────────────────────────────────────────────

/**
 * The document a save sends. An edit starts from the loaded document
 * (`specDocument`: legacy `variables` and labels kept, the read's extras
 * dropped); the name of a loaded flavor never changes.
 */
export function buildDocument(draft: FlavorDraft, loaded: ClusterSpec | null): ClusterSpec {
  const base: ClusterSpec = loaded
    ? specDocument(loaded)
    : {
        apiVersion: "wingman.io/v1",
        kind: "ClusterSpec",
        metadata: { name: "", description: "", version: "", labels: {} },
        spec: { day1: { variables: [], structure: {}, locked_paths: [], template: "", values: {} }, day2: { addons: [] } },
      };
  // The draft's ratio replaces the stored one; off, the document has none
  const day1 = { ...base.spec.day1 };
  delete day1.nodepool_ratio;
  return {
    ...base,
    metadata: {
      ...base.metadata,
      name: loaded ? loaded.metadata.name : draft.name.trim(),
      version: draft.version.trim(),
      description: draft.description.trim(),
    },
    spec: {
      day1: {
        ...day1,
        structure: draft.structure,
        locked_paths: draft.locked,
        template: "",
        values: draft.values,
        // Numbers as day1 reads them; a part not typed as one is sent as typed, and day1 says why
        ...(draft.ratio.length > 0 ? { nodepool_ratio: draft.ratio.map(ratioValue) as number[] } : {}),
      },
      day2: { addons: draft.addons },
    },
  };
}

/** The document as the file stores it: the shared template is never in it. */
export function storedForm(spec: ClusterSpec): unknown {
  const day1: Partial<ClusterSpec["spec"]["day1"]> = { ...spec.spec.day1 };
  delete day1.template;
  return { ...spec, spec: { ...spec.spec, day1 } };
}

// ── Checks (day1's, for instant feedback) ───────────────────────────────────

const OWNER = /^[0-9]{1,10}$/;
const OWNER_HINT = "A number of 1 to 10 digits, like 1234";
const LOCK_NEEDS_VALUE = "A locked value needs a value: set one, or make it a preset";

export interface Issue {
  path: string;
  message: string;
  /** For a config list: the entry it is about, which the list editor shows itself. */
  entry?: number;
}

/**
 * Every problem the draft has that day1 would refuse at save, at the path
 * of the field it belongs to. Config entries are checked by the config list
 * editor where they are shown; they are counted here, at their list's path.
 */
export function draftIssues(
  draft: FlavorDraft,
  catalog: MachineConfigs | undefined,
  checks: { name?: (name: string) => string | null; version: (version: string) => string | null }
): Issue[] {
  const issues: Issue[] = [];
  const add = (path: string, message: string | null, entry?: number) => message && issues.push({ path, message, entry });
  if (checks.name) add("metadata.name", checks.name(draft.name.trim()));
  add("metadata.version", checks.version(draft.version.trim()));

  for (const { path } of OWNERS) {
    const value = draft.values[path];
    if (value === undefined || value === "") {
      if (isLocked(draft, path)) add(path, LOCK_NEEDS_VALUE);
    } else if (typeof value !== "string" || !OWNER.test(value)) add(path, OWNER_HINT);
  }
  const platform = draft.values[PLATFORM];
  if (isLocked(draft, PLATFORM) && (platform === undefined || platform === "")) add(PLATFORM, LOCK_NEEDS_VALUE);

  const rule = configsMode(draft) === "rule";
  for (let i = 0; i < nodepoolCount(draft); i++) {
    const pool = nodepoolValues(draft, i);
    const replicas = nodepoolPath(i, "replicas");
    if (pool.replicas === undefined || pool.replicas === "") {
      if (isLocked(draft, replicas)) add(replicas, LOCK_NEEDS_VALUE);
    } else if (!isWholeNumber(pool.replicas)) add(replicas, "A whole number, like 3");

    if (draft.ratio.length > 0) {
      const part = (draft.ratio[i] ?? "").trim();
      if (!/^\d+$/.test(part) || Number(part) < 1 || Number(part) > 100) add(nodepoolPath(i, "ratio"), RATIO_HINT);
      if (isLocked(draft, replicas)) add(replicas, "The ratio sizes this nodepool: make its replicas a preset, not locked");
      const parts = ratioParts(draft);
      if (parts && isWholeNumber(pool.replicas) && Number(pool.replicas) % parts[i] !== 0) {
        add(replicas, `A multiple of ${parts[i]}, this nodepool's part of ${ratioLabel(draft)}`);
      }
    }

    const configs = nodepoolPath(i, "configs");
    const entries = asEntries(pool.configs);
    if (rule) {
      const hardware = hardwareOf(entries);
      if (!hardware) add(configs, "Choose this nodepool's network hardware");
      else if (catalog && !catalog.hardware_types.some((h) => h.name === hardware)) add(configs, `No hardware type '${hardware}'`);
    } else {
      entryProblems(entries, catalog).forEach((problems, j) =>
        problems.forEach((p) => add(configs, `Config ${j + 1}: ${p}`, j))
      );
    }
  }
  if (rule) {
    const shared = ruleEntries(draft);
    const networks = shared.filter(isNetworkEntry).length;
    if (networks !== 1) {
      add(CONFIGS_RULE, `List ${NETWORK_CONFIG} exactly once: every nodepool needs its own network config`);
    }
    entryProblems(shared, catalog, { hardwareRequired: false }).forEach((problems, j) =>
      problems.forEach((p) => add(CONFIGS_RULE, `Config ${j + 1}: ${p}`, j))
    );
  }
  return issues;
}

function isWholeNumber(value: unknown): boolean {
  if (typeof value === "number") return Number.isInteger(value) && value >= 0;
  return typeof value === "string" && /^\d+$/.test(value);
}

// ── Day1's problems at their fields ─────────────────────────────────────────

/** A problem's subject (`owner_anaf`, `nodepools[1].configs[0]`) and the rest of it. */
function problemSubject(problem: string): { path: string; message: string } | null {
  const lock = /^locked_paths: '?([^\s']+)'?\s(.*)$/.exec(problem);
  if (lock) return { path: lock[1], message: `${lock[1]} ${lock[2]}` };
  const at = problem.indexOf(": ");
  if (at <= 0) return null;
  const head = problem.slice(0, at);
  if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]+\])*$/.test(head)) return null;
  return { path: head, message: problem.slice(at + 2) };
}

export interface RoutedProblem {
  /** The field it is shown at. */
  field: string;
  /** The problem's own path: the field's, or one inside it (`nodepools[0].configs[2]`). */
  path: string;
  message: string;
  /** The problem as day1 wrote it. */
  raw: string;
}

/**
 * Attach each problem to the deepest field whose path is the problem's or
 * contains it; the rest have no field and are listed at the top.
 */
export function routeProblems(problems: string[], fields: string[]): { routed: RoutedProblem[]; unmatched: string[] } {
  const routed: RoutedProblem[] = [];
  const unmatched: string[] = [];
  for (const raw of problems) {
    const subject = problemSubject(raw);
    const field = subject
      ? fields
          .filter((f) => subject.path === f || subject.path.startsWith(`${f}.`) || subject.path.startsWith(`${f}[`))
          .sort((a, b) => b.length - a.length)[0]
      : undefined;
    if (subject && field) routed.push({ field, path: subject.path, message: subject.message, raw });
    else unmatched.push(raw);
  }
  return { routed, unmatched };
}

// ── What every cluster gets (the review's summary) ──────────────────────────

export interface ValueLine {
  path: string;
  label: string;
  value: string;
}

export function pathLabel(path: string): string {
  if (path === CONFIGS_RULE) return "Every nodepool · Machine configs";
  const owner = OWNERS.find((o) => o.path === path);
  if (owner) return `Owner · ${owner.label}`;
  const pool = /^nodepools\[(\d+)\]\.(.+)$/.exec(path);
  if (pool) return `Nodepool ${Number(pool[1]) + 1} · ${inputLabel(pool[2])}`;
  return inputLabel(path);
}

/** `node_labels` → `Node labels`. */
export function inputLabel(name: string): string {
  if (name === "configs") return "Machine configs";
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function showValue(value: unknown): string {
  if (value === undefined || value === null) return "—";
  if (Array.isArray(value)) {
    const entries = asEntries(value);
    if (entries.length === value.length && entries.length > 0) {
      return entries.map((e) => (isNetworkEntry(e) ? `${NETWORK_CONFIG}${e.hardware ? ` (${e.hardware})` : ""}` : e.name)).join(", ");
    }
    return value.length === 0 ? "none" : JSON.stringify(value);
  }
  if (isMapping(value)) {
    const keys = Object.entries(value);
    return keys.length === 0 ? "none" : keys.map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");
  }
  return String(value);
}

/** Locked and preset values, each as one line, in the order the page shows them. */
export function valueLines(draft: FlavorDraft): { locked: ValueLine[]; presets: ValueLine[] } {
  const locked: ValueLine[] = [];
  const presets: ValueLine[] = [];
  const put = (path: string, value: unknown, label = pathLabel(path)) =>
    (isLocked(draft, path) ? locked : presets).push({ path, label, value: showValue(value) });
  const rule = configsMode(draft) === "rule";
  for (const [key, value] of Object.entries(draft.values)) {
    if (key === "nodepools" || value === undefined) continue;
    put(key, value);
  }
  if (rule) {
    locked.push({
      path: CONFIGS_RULE,
      label: pathLabel(CONFIGS_RULE),
      value: ruleEntries(draft).map((e) => (isNetworkEntry(e) ? `${NETWORK_CONFIG} (each nodepool's hardware)` : e.name)).join(", "),
    });
  }
  for (let i = 0; i < nodepoolCount(draft); i++) {
    for (const [key, value] of Object.entries(nodepoolValues(draft, i))) {
      const path = nodepoolPath(i, key);
      if (rule && key === "configs") {
        presets.push({ path, label: `Nodepool ${i + 1} · Network hardware`, value: hardwareOf(asEntries(value)) ?? "—" });
      } else put(path, value);
    }
  }
  return { locked, presets };
}

// ── Saved locks a create does not enforce ───────────────────────────────────

/**
 * Why a saved lock on `path` is not enforced: it is in `locked_paths` but
 * not in `enforced_locks` (a flavor without the field enforces them all).
 * The reason is the flavor's warning about it; `undefined` when it is
 * enforced, or not a saved lock.
 */
export function lockNotEnforced(
  saved: { spec: ClusterSpec["spec"]; enforced_locks?: string[]; warnings?: string[] } | null | undefined,
  path: string
): string | undefined {
  const locked = saved?.spec.day1.locked_paths ?? [];
  if (!saved || !locked.includes(path)) return undefined;
  if ((saved.enforced_locks ?? locked).includes(path)) return undefined;
  const warning = (saved.warnings ?? []).map(problemSubject).find((s) => s?.path === path);
  return warning?.message ?? "the saved lock breaks a rule a save checks";
}

// ── Locks the editor cannot show (old files, broken saves) ──────────────────

/** Stored locks with no control here: not lockable, or on a nodepool the flavor does not have. */
export function strayLocks(draft: FlavorDraft): string[] {
  const count = nodepoolCount(draft);
  return draft.locked.filter((path) => {
    if (!isLockable(path)) return true;
    const pool = /^nodepools\[(\d+)\]\./.exec(path);
    return pool !== null && Number(pool[1]) >= count;
  });
}

// ── The cluster-file preview (`POST /clusters/preview`) ─────────────────────

const LEGACY_IDENTITY = ["cluster_name", "site", "site_name", "mce", "mce_name"];

/** `ocp4-<env>-flavor-preview-<site>`: a name the MCE's convention accepts. */
export function sampleClusterName(mce: Mce): string {
  return `ocp4-${mce.env ?? "prod"}-flavor-preview-${mce.site}`;
}

function sampleFor(field: TemplateField): unknown {
  if (field.example) return field.type === "integer" && /^\d+$/.test(field.example) ? Number(field.example) : field.example;
  if (field.type === "integer") return 1;
  return `example-${field.name.replace(/_/g, "-")}`;
}

function sameLockValue(a: unknown, b: unknown): boolean {
  if (typeof a === "number" && typeof b === "string") return String(a) === b;
  if (typeof a === "string" && typeof b === "number") return a === String(b);
  return sameValues(a, b);
}

export interface PreviewPlan {
  request: CreateClusterRequest;
  /** Inputs each cluster sets that the flavor leaves open, filled with examples. */
  samples: string[];
  /** Saved locks whose value the draft changes: day1 renders the saved value. */
  asSaved: string[];
}

/**
 * The preview of a saved flavor with the draft's values. Day1 renders only a
 * flavor that is in the specs repo, at its saved version, and enforces the
 * saved locks: a changed locked value is sent as saved (and listed), since
 * sending another would be refused. Inputs each cluster sets get examples.
 */
export function previewPlan(args: {
  draft: FlavorDraft;
  saved: ClusterSpec;
  schema: TemplateField[];
  mce: Mce;
  openshiftVersion: string;
  clusterName: string;
}): PreviewPlan {
  const { draft, saved, schema, mce, openshiftVersion, clusterName } = args;
  const variables: Values = clone(draft.values);
  for (const key of LEGACY_IDENTITY) delete variables[key];
  const samples: string[] = [];
  const asSaved: string[] = [];

  for (const field of schema) {
    if (PER_CLUSTER.has(field.name) || !field.required) continue;
    if (field.name === "nodepools" && field.type === "list") {
      const count = Math.max(1, nodepoolCount(draft));
      const pools = Array.from({ length: count }, (_, i) => ({ ...(poolList(variables)[i] ?? {}) }));
      if (nodepoolCount(draft) === 0) samples.push("nodepools[0]");
      pools.forEach((pool, i) => {
        for (const sub of field.fields ?? []) {
          if (!sub.required || (pool[sub.name] !== undefined && pool[sub.name] !== "")) continue;
          pool[sub.name] = sampleFor(sub);
          samples.push(nodepoolPath(i, sub.name));
        }
      });
      variables.nodepools = pools;
      continue;
    }
    if (variables[field.name] === undefined || variables[field.name] === "") {
      variables[field.name] = sampleFor(field);
      samples.push(field.name);
    }
  }

  const savedValues = saved.spec.day1.values ?? {};
  for (const path of saved.spec.day1.locked_paths ?? []) {
    if (path === CONFIGS_RULE) {
      const savedPools = poolList(savedValues);
      const ruleSaved = asEntries(savedPools[0]?.configs);
      const pools = poolList(variables);
      const matches = pools.every((p) => {
        const sent = asEntries(p.configs);
        return sent.length === 0 || sameConfigNames(sent, ruleSaved);
      });
      if (!matches && ruleSaved.length > 0) {
        variables.nodepools = pools.map((p, i) => ({ ...p, configs: savedPools[i]?.configs ?? savedPools[0]?.configs }));
        asSaved.push(path);
      }
      continue;
    }
    if (!isLockable(path)) continue;
    const top = !path.startsWith("nodepools[");
    const pool = /^nodepools\[(\d+)\]\.(\w+)$/.exec(path);
    const want = top ? savedValues[path] : pool ? poolList(savedValues)[Number(pool[1])]?.[pool[2]] : undefined;
    if (want === undefined) continue;
    if (top) {
      if (!sameLockValue(variables[path], want)) {
        variables[path] = want;
        asSaved.push(path);
      }
    } else if (pool) {
      const pools = poolList(variables);
      const target = pools[Number(pool[1])];
      if (target && !sameLockValue(target[pool[2]], want)) {
        variables.nodepools = pools.map((p, i) => (i === Number(pool[1]) ? { ...p, [pool[2]]: want } : p));
        asSaved.push(path);
      }
    }
  }

  // Day1 enforces the saved ratio: replicas off it are sent at size 1 (ADR-0040)
  const savedRatio = saved.spec.day1.nodepool_ratio ?? [];
  const sizedPools = poolList(variables);
  if (savedRatio.length > 0 && sizedPools.length >= savedRatio.length) {
    const replicas = savedRatio.map((_, i) => Number(sizedPools[i].replicas));
    const size = replicas[0] / savedRatio[0];
    if (!(Number.isInteger(size) && size >= 1 && replicas.every((r, i) => r === savedRatio[i] * size))) {
      variables.nodepools = sizedPools.map((p, i) => (i < savedRatio.length ? { ...p, replicas: savedRatio[i] } : p));
      savedRatio.forEach((_, i) => samples.push(nodepoolPath(i, "replicas")));
    }
  }

  variables.openshift_release_version = openshiftVersion;
  return {
    request: {
      name: clusterName,
      site: mce.site,
      mce: mce.name,
      spec_name: saved.metadata.name,
      spec_version: saved.metadata.version,
      variables,
    },
    samples,
    asSaved,
  };
}

function sameConfigNames(a: ConfigEntry[], b: ConfigEntry[]): boolean {
  const names = (list: ConfigEntry[]) => list.map((e) => e.name).sort().join("\u0000");
  return names(a) === names(b);
}

/** The release to preview with: the flavor's preset, else the MCE's default, else the newest offered. */
export function previewRelease(preset: unknown, mce: Mce | undefined, offered: string[]): string | null {
  const bare = (v: unknown) => (typeof v === "string" ? v.trim().replace(/-x86_64$/, "") : "");
  for (const candidate of [bare(preset), bare(mce?.default_mastertag)]) {
    if (candidate && offered.includes(candidate)) return candidate;
  }
  return offered[0] ?? null;
}
