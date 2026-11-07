/**
 * Helm values as plain data: leaves, paths and YAML.
 *
 * A path is an array of keys, never a dotted string: chart values often have
 * keys with dots in them (`app.kubernetes.io/name`), which a dotted path
 * would silently split. Arrays and scalars are leaves, as they are for Helm's
 * merge (an array is replaced, not merged).
 */

import jsYaml from "js-yaml";

export type Values = Record<string, unknown>;
export type ValuePath = readonly string[];

export interface Leaf {
  path: ValuePath;
  value: unknown;
}

export function isMapping(value: unknown): value is Values {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Every leaf, depth first in key order. An empty mapping is a leaf of its own. */
export function leaves(values: Values, prefix: ValuePath = []): Leaf[] {
  const out: Leaf[] = [];
  for (const [key, value] of Object.entries(values)) {
    const path = [...prefix, key];
    if (isMapping(value) && Object.keys(value).length > 0) out.push(...leaves(value, path));
    else out.push({ path, value });
  }
  return out;
}

export function getAt(values: unknown, path: ValuePath): unknown {
  let cursor = values;
  for (const key of path) {
    if (!isMapping(cursor) || !(key in cursor)) return undefined;
    cursor = cursor[key];
  }
  return cursor;
}

export function hasAt(values: unknown, path: ValuePath): boolean {
  let cursor = values;
  for (const key of path) {
    if (!isMapping(cursor) || !(key in cursor)) return false;
    cursor = cursor[key];
  }
  return true;
}

/** A copy of `values` with `value` at `path`, creating mappings on the way. */
export function setAt(values: Values, path: ValuePath, value: unknown): Values {
  const [key, ...rest] = path;
  if (key === undefined) return values;
  if (rest.length === 0) return { ...values, [key]: value };
  const child = isMapping(values[key]) ? (values[key] as Values) : {};
  return { ...values, [key]: setAt(child, rest, value) };
}

/** A copy of `values` without `path`; mappings it leaves empty are removed too. */
export function unsetAt(values: Values, path: ValuePath): Values {
  const [key, ...rest] = path;
  if (key === undefined || !(key in values)) return values;
  const { [key]: child, ...others } = values;
  if (rest.length === 0) return others;
  if (!isMapping(child)) return values;
  const pruned = unsetAt(child, rest);
  return Object.keys(pruned).length === 0 ? others : { ...others, [key]: pruned };
}

/**
 * The role (or file) that set `path`, from a provenance tree with the
 * values' shape. A string above the leaf covers everything below it.
 */
export function sourceAt(provenance: unknown, path: ValuePath): string | undefined {
  let cursor = provenance;
  for (const key of path) {
    if (typeof cursor === "string") return cursor;
    if (!isMapping(cursor) || !(key in cursor)) return undefined;
    cursor = cursor[key];
  }
  return typeof cursor === "string" ? cursor : undefined;
}

/** JSON with sorted keys: equal values give equal strings. */
export function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (isMapping(value)) {
    const keys = Object.keys(value).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

export function sameValues(a: unknown, b: unknown): boolean {
  return stableStringify(a) === stableStringify(b);
}

export function pathLabel(path: ValuePath): string {
  return path.join(".");
}

/** A values file as YAML; an empty mapping is an empty file. */
export function toYaml(values: unknown): string {
  if (isMapping(values) && Object.keys(values).length === 0) return "";
  return jsYaml.dump(values, { indent: 2, lineWidth: -1, noRefs: true });
}

export type ParsedValues = { ok: true; values: Values } | { ok: false; error: string };

/** Parse a values file: a mapping, or nothing (an empty file is `{}`). */
export function parseValuesYaml(text: string): ParsedValues {
  let doc: unknown;
  try {
    doc = jsYaml.load(text);
  } catch (e) {
    const reason = e instanceof jsYaml.YAMLException ? e.reason : String(e);
    const line = e instanceof jsYaml.YAMLException && e.mark ? ` (line ${e.mark.line + 1})` : "";
    return { ok: false, error: `Invalid YAML${line}: ${reason}` };
  }
  if (doc === undefined || doc === null) return { ok: true, values: {} };
  if (!isMapping(doc)) return { ok: false, error: "A values file must be a mapping (key: value)" };
  return { ok: true, values: doc };
}

/** A one-line YAML rendering for read-only cells. */
export function inlineYaml(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value !== "object") return String(value);
  return jsYaml.dump(value, { flowLevel: 0, lineWidth: -1, noRefs: true }).trim();
}
