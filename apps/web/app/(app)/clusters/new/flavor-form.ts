/**
 * What a flavor (a cluster spec) sets on the create form in flavors v2:
 * locked values, presets, the configs rule and the nodepool defaults
 * (docs/notes/2026-11-08-flavors-v2-api-changes.md §1-§6 and §9; ADR-0026 to
 * ADR-0029). Day1 is the authority and checks all of it again: this mirrors
 * its rules so the form shows what day1 will accept, and every problem day1
 * returns is still shown, at its field when the form has that field.
 */

import { seedFromStructure, type FieldValue, type FieldValueMap, type FormValues } from "@/components/clusters/dynamic-variable-form";
import { configProblems } from "@/components/machine-configs/config-list-editor";
import { asEntries, cleanEntry, defaultConfigs, entryProblems, isNetworkEntry, NETWORK_CONFIG } from "@/lib/machine-configs";
import type { ConfigEntry, MachineConfigs, SpecEntry, TemplateField } from "@/types";

/** The template inputs day1's locks know by name (`wingman_day1.domain.locks.LOCKABLE`). */
export const NODEPOOLS = "nodepools";
export const CONFIGS = "configs";
/** The one rule path (§9): every nodepool's configs. */
export const CONFIGS_RULE = "nodepools[*].configs";
export const OWNER_INPUTS: readonly string[] = ["owner_merkaz", "owner_anaf", "owner_mador"];

const isMap = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

// ── Paths (§2) ────────────────────────────────────────────────────────────────

type Segment = string | number;

/** `nodepools[1].configs` → `["nodepools", 1, "configs"]`; `null` when it is not a path of §2 (no `[*]`). */
export function pathSegments(path: string): Segment[] | null {
  const head = /^[A-Za-z_][A-Za-z0-9_]*/.exec(path);
  if (!head) return null;
  const segments: Segment[] = [head[0]];
  let rest = path.slice(head[0].length);
  while (rest) {
    const step = /^(?:\.([A-Za-z_][A-Za-z0-9_]*)|\[(0|[1-9][0-9]{0,2})\])/.exec(rest);
    if (!step) return null;
    segments.push(step[1] ?? Number(step[2]));
    rest = rest.slice(step[0].length);
  }
  return segments;
}

/** The value at `path`; `undefined` when the path is missing (or not a path). */
export function lookup(root: unknown, path: string): unknown {
  const segments = pathSegments(path);
  if (!segments) return undefined;
  let node: unknown = root;
  for (const segment of segments) {
    if (typeof segment === "number" ? !Array.isArray(node) : !isMap(node)) return undefined;
    node = (node as Record<string | number, unknown>)[segment];
    if (node === undefined) return undefined;
  }
  return node;
}

/** `root` with `value` at `path`, where every parent already exists; `root` unchanged otherwise. */
function assignExisting(root: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const segments = pathSegments(path);
  if (!segments) return root;
  const put = (node: unknown, rest: Segment[]): unknown => {
    const [segment, ...tail] = rest;
    if (typeof segment === "number") {
      if (!Array.isArray(node) || segment >= node.length) return node;
      return node.map((item, i) => (i === segment ? (tail.length ? put(item, tail) : value) : item));
    }
    if (!isMap(node)) return node;
    if (tail.length === 0) return { ...node, [segment]: value };
    return segment in node ? { ...node, [segment]: put(node[segment], tail) } : node;
  };
  return put(root, segments) as Record<string, unknown>;
}

export const nodepoolConfigsPath = (index: number) => `${NODEPOOLS}[${index}].${CONFIGS}`;

/** `nodepools[<i>].configs`: a field the form draws with the machine-config picker. */
export function isConfigsPath(path: string): boolean {
  return /^nodepools\[\d+\]\.configs$/.test(path);
}

// ── Locks (§6, §9) ────────────────────────────────────────────────────────────

/** What day1 lets a flavor lock (§6); anything else it lists in `warnings` and does not enforce. */
const LOCKABLE = [
  /^owner_(merkaz|anaf|mador)$/,
  /^platform$/,
  /^nodepools\[(0|[1-9][0-9]{0,2})\]\.(replicas|configs|node_labels)$/,
];

export interface FlavorLocks {
  /** Each positional lock day1 enforces, with the flavor's value (sent as it is). */
  values: ReadonlyMap<string, unknown>;
  /** The configs rule's entries (`{name}` each; `nm-conf` is each nodepool's own); `null` without a rule day1 enforces. */
  rule: ConfigEntry[] | null;
}

/**
 * The rule's value (ADR-0029): the configs of every nodepool the flavor sets,
 * which must agree by name and list `nm-conf` once; `null` when they don't
 * (day1 then reports the rule in `warnings` and does not enforce it).
 */
function ruleEntries(values: Record<string, unknown>): ConfigEntry[] | null {
  const pools = values[NODEPOOLS];
  if (!Array.isArray(pools) || pools.length === 0) return null;
  const lists = pools.map((pool) => (isMap(pool) && Array.isArray(pool[CONFIGS]) ? pool[CONFIGS] : null));
  if (lists.some((list) => list === null)) return null;
  const names = (list: unknown[]) =>
    list.map((entry) => (isMap(entry) && typeof entry.name === "string" && entry.name ? entry.name : JSON.stringify(entry)));
  const first = names(lists[0]!);
  const sorted = (items: string[]) => [...items].sort().join("\u0000");
  if (lists.some((list) => sorted(names(list!)) !== sorted(first))) return null;
  if (first.filter((name) => name === NETWORK_CONFIG).length !== 1) return null;
  return first.map((name) => ({ name }));
}

/**
 * The locks day1 enforces for this flavor: its `enforced_locks` (§5). A day1
 * that predates that field is answered by the same rules, repeated here.
 */
export function flavorLocks(spec: SpecEntry): FlavorLocks {
  const values = spec.spec.day1.values ?? {};
  const locked = new Map<string, unknown>();
  let rule: ConfigEntry[] | null = null;
  for (const path of spec.enforced_locks ?? spec.spec.day1.locked_paths ?? []) {
    if (path === CONFIGS_RULE) {
      rule = ruleEntries(values);
      continue;
    }
    if (!LOCKABLE.some((shape) => shape.test(path))) continue;
    const value = lookup(values, path);
    if (value !== undefined) locked.set(path, value);
  }
  // The rule covers every nodepool: a position's configs lock beside it is not enforced
  if (rule) for (const path of [...locked.keys()]) if (isConfigsPath(path)) locked.delete(path);
  return { values: locked, rule };
}

// ── Seeding the form ──────────────────────────────────────────────────────────

/** The template's `nodepools` list and its `configs` field, when it has them. */
function nodepoolFields(schema: TemplateField[]): { fields: TemplateField[]; configs: boolean } | null {
  const pools = schema.find((f) => f.name === NODEPOOLS && f.type === "list" && f.fields?.length);
  if (!pools?.fields) return null;
  return { fields: pools.fields, configs: pools.fields.some((f) => f.name === CONFIGS && f.type === "list") };
}

/** Config entries as the form keeps them: `hardware` only on a network entry that has one. */
export function formEntries(entries: ConfigEntry[]): FieldValueMap[] {
  return entries.map((e): FieldValueMap =>
    isNetworkEntry(e) && e.hardware ? { name: e.name, hardware: e.hardware } : { name: e.name }
  );
}

/** The configs a nodepool without the flavor's starts with: the rule's names, else the nodepool defaults (§1). */
function startingConfigs(locks: FlavorLocks, catalog: MachineConfigs | undefined): FieldValueMap[] {
  return formEntries(locks.rule ?? defaultConfigs(catalog));
}

/** A nodepool added in the form: the template's defaults, with the starting configs. */
export function newNodepool(schema: TemplateField[], locks: FlavorLocks, catalog: MachineConfigs | undefined): FieldValueMap {
  const pools = nodepoolFields(schema);
  const pool = seedFromStructure({}, pools?.fields ?? []);
  return pools?.configs ? { ...pool, [CONFIGS]: startingConfigs(locks, catalog) } : pool;
}

export interface CreateFormSeed {
  values: FormValues;
  /** The nodepools the flavor sets; the form adds more, but cannot remove these. */
  fixedNodepools: number;
}

/**
 * The form a flavor starts: its `structure` (the number of nodepools), its
 * values in place (presets and locked values, per nodepool), and every
 * nodepool whose configs the flavor does not set filled with the rule's
 * names or the nodepool defaults. Presets are merged under what the form
 * sends, and a sent list replaces the flavor's, so the form must start from
 * them rather than leave them blank.
 */
export function seedCreateForm(
  spec: SpecEntry,
  schema: TemplateField[],
  locks: FlavorLocks,
  catalog: MachineConfigs | undefined
): CreateFormSeed {
  const presets = spec.spec.day1.values ?? {};
  const seeded = seedFromStructure(spec.spec.day1.structure ?? {}, schema);
  for (const field of schema) {
    if (!(field.name in presets)) continue;
    const preset = presets[field.name];
    const current = seeded[field.name];
    if (field.type === "list" && field.fields?.length && Array.isArray(preset) && Array.isArray(current)) {
      // Per item: the structure's fields, then what the flavor sets on that item
      seeded[field.name] = Array.from({ length: Math.max(current.length, preset.length) }, (_, i) => ({
        ...(isMap(current[i]) ? (current[i] as FieldValueMap) : seedFromStructure({}, field.fields!)),
        ...(isMap(preset[i]) ? (preset[i] as FieldValueMap) : {}),
      }));
    } else {
      seeded[field.name] = preset as FieldValue;
    }
  }
  const pools = nodepoolFields(schema);
  const items = Array.isArray(seeded[NODEPOOLS]) ? (seeded[NODEPOOLS] as FieldValue[]) : [];
  if (pools?.configs) {
    seeded[NODEPOOLS] = items.map((item, i) =>
      isMap(item) && !Array.isArray(lookup(presets, nodepoolConfigsPath(i)))
        ? { ...item, [CONFIGS]: startingConfigs(locks, catalog) }
        : item
    );
  }
  return { values: seeded, fixedNodepools: pools ? items.length : 0 };
}

/**
 * The fields the flavor prefills and leaves editable. Under the rule a
 * nodepool's configs are not a preset (their names are locked) although the
 * hardware type in them is.
 */
export function presetPaths(spec: SpecEntry, schema: TemplateField[], locks: FlavorLocks): Set<string> {
  const presets = spec.spec.day1.values ?? {};
  const paths = new Set<string>();
  const add = (path: string) => {
    if (locks.values.has(path) || (locks.rule && isConfigsPath(path))) return;
    paths.add(path);
  };
  for (const field of schema) {
    const value = presets[field.name];
    if (value === undefined) continue;
    if (field.type === "list" && field.fields?.length && Array.isArray(value)) {
      value.forEach((item, i) => {
        if (!isMap(item)) return;
        for (const sub of field.fields!) if (item[sub.name] !== undefined) add(`${field.name}[${i}].${sub.name}`);
      });
    } else {
      add(field.name);
    }
  }
  return paths;
}

// ── The request ───────────────────────────────────────────────────────────────

/**
 * The template inputs to send: config entries as §3 writes them, owners as
 * text (§4), and every locked value exactly as the flavor has it (day1
 * compares them as JSON, so `{hardware: null}` would not be the same value).
 */
export function requestVariables(form: FormValues, locks: FlavorLocks): Record<string, unknown> {
  let vars: Record<string, unknown> = structuredClone(form);
  const pools = vars[NODEPOOLS];
  if (Array.isArray(pools)) {
    vars[NODEPOOLS] = pools.map((pool) =>
      isMap(pool) && Array.isArray(pool[CONFIGS]) ? { ...pool, [CONFIGS]: asEntries(pool[CONFIGS]).map(cleanEntry) } : pool
    );
  }
  for (const owner of OWNER_INPUTS) {
    if (typeof vars[owner] === "number" && !locks.values.has(owner)) vars[owner] = String(vars[owner]);
  }
  for (const [path, value] of locks.values) vars = assignExisting(vars, path, structuredClone(value));
  return vars;
}

// ── Checks before the request ─────────────────────────────────────────────────

const OWNER = /^[0-9]{1,10}$/;

/** Why day1 would refuse this owner (ADR-0028); `null` when it is fine or still empty (required is checked apart). */
export function ownerProblem(value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  const text = String(value);
  if (OWNER.test(text)) return null;
  if (/^[0-9]+$/.test(text)) return `At most 10 digits (this is ${text.length})`;
  return "Digits 0-9 only, like 1234";
}

/** Each editable owner's problem, by path, as the form shows it while typing. */
export function ownerProblems(form: FormValues, schema: TemplateField[], locks: FlavorLocks): Record<string, string> {
  const found: Record<string, string> = {};
  for (const owner of OWNER_INPUTS) {
    if (!schema.some((f) => f.name === owner) || locks.values.has(owner)) continue;
    const problem = ownerProblem(form[owner]);
    if (problem) found[owner] = problem;
  }
  return found;
}

/**
 * What stops the review before day1 is asked, one line each: an owner that is
 * not a number, a config entry the catalogue says day1 would refuse (no
 * hardware type, an unknown name, the same entry twice). A locked list is the
 * flavor's: day1 alone judges it.
 */
export function flavorProblems(
  form: FormValues,
  schema: TemplateField[],
  locks: FlavorLocks,
  catalog: MachineConfigs | undefined,
  label: (path: string) => string
): string[] {
  const lines = Object.entries(ownerProblems(form, schema, locks)).map(([path, p]) => `${label(path)}: ${p}`);
  const pools = form[NODEPOOLS];
  if (!Array.isArray(pools)) return lines;
  pools.forEach((pool, i) => {
    const path = nodepoolConfigsPath(i);
    if (!isMap(pool) || !Array.isArray(pool[CONFIGS]) || locks.values.has(path)) return;
    const entries = asEntries(pool[CONFIGS]);
    entryProblems(entries, catalog).forEach((problems, j) => {
      const name = entries[j]?.name || "new entry";
      for (const problem of problems) lines.push(`${label(path)} › ${name}: ${problem}`);
    });
  });
  return lines;
}

// ── Day1's problems, placed at their fields ───────────────────────────────────

/** Every field the form draws, by template-input path; config lists are one field (their entries are the picker's). */
export function fieldPaths(schema: TemplateField[], values: Record<string, unknown>, prefix = ""): Set<string> {
  const paths = new Set<string>();
  for (const field of schema) {
    const path = prefix ? `${prefix}.${field.name}` : field.name;
    paths.add(path);
    const value = values[field.name];
    if (field.type === "list" && field.fields?.length && Array.isArray(value) && !isConfigsPath(path)) {
      value.forEach((item, i) => {
        if (isMap(item)) for (const sub of fieldPaths(field.fields!, item, `${path}[${i}]`)) paths.add(sub);
      });
    }
  }
  return paths;
}

/** `<path>: <message>`, the shape of each of day1's problems (§2); a node label key may sit in `[...]`. */
const PROBLEM = /^([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]\s]*\])*):\s+([\s\S]*)$/;

export interface PlacedProblems {
  /** By field path: the message alone when it is about the field, the whole line when about a part of it. */
  byField: Record<string, string[]>;
  /** A config list's problems by entry index (`nodepools[1].configs[0]: ...`). */
  byEntry: Record<string, Record<number, string[]>>;
  /** The lines no field of the form is about, for the list above the submit button. */
  rest: string[];
  /** How many lines went to a field. */
  placed: number;
}

/**
 * Put each of day1's problems at the field it starts with: the longest field
 * path the problem's path begins with. `nodepool[0]: ...` (a file key),
 * `nodepools[*].configs: ...` and `nodepools[2].replicas: ...` on a form with
 * two nodepools stay in `rest`: no field of the form is about them.
 */
export function placeProblems(lines: string[], fields: ReadonlySet<string>): PlacedProblems {
  const placed: PlacedProblems = { byField: {}, byEntry: {}, rest: [], placed: 0 };
  for (const line of lines) {
    const match = PROBLEM.exec(line);
    const token = match?.[1] ?? "";
    const cuts = [token.length, ...[...token.matchAll(/[.[]/g)].map((m) => m.index).reverse()];
    const field = match ? cuts.map((cut) => token.slice(0, cut)).find((prefix) => fields.has(prefix)) : undefined;
    // An item of a list the form does not draw (`nodepools[2]` of two) is not about the list's field
    const item = field !== undefined && !isConfigsPath(field) && /^\[(\d+|\*)\]/.test(token.slice(field.length));
    if (!match || !field || item) {
      placed.rest.push(line);
      continue;
    }
    placed.placed += 1;
    if (field === token) {
      (placed.byField[field] ??= []).push(match[2]);
      continue;
    }
    if (isConfigsPath(field)) {
      const entries = configProblems([line], field);
      const [index] = Object.keys(entries);
      if (index !== undefined) {
        const byIndex = (placed.byEntry[field] ??= {});
        (byIndex[Number(index)] ??= []).push(...entries[Number(index)]);
        continue;
      }
    }
    (placed.byField[field] ??= []).push(line);
  }
  return placed;
}
