/**
 * A nodepool that draws Agents from several InfraEnvs (ADR-0064).
 *
 * Its own InfraEnv stays `infraEnvName` (the template input `infra_env`): it
 * names the NodePool, `<clusterName>-<infraEnvName>`. The others are
 * `additionalInfraEnvNames` (the input `additional_infra_envs`). Day1 offers
 * the input in the template schema only when `DAY1_MULTI_INFRAENV_NODEPOOLS`
 * is on and the specs project's template reads it, so the schema is the one
 * switch the web reads.
 */

import jsYaml from "js-yaml";
import type { TemplateField } from "@/types";

export const INFRA_ENVS_INPUT = "additional_infra_envs";
const INFRA_ENVS_KEY = "additionalInfraEnvNames";
/** The most InfraEnvs a nodepool draws from beside its own (day1's limit). */
export const MAX_ADDITIONAL = 16;
const DNS_LABEL = /^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$/;

/** Whether the form offers a nodepool's other InfraEnvs: day1's schema lists the input. */
export function offersInfraEnvs(schema: readonly TemplateField[] | undefined): boolean {
  const nodepools = schema?.find((f) => f.name === "nodepools");
  return Boolean(nodepools?.fields?.some((f) => f.name === INFRA_ENVS_INPUT));
}

/** Whether `path` is a nodepool's `additional_infra_envs` (`nodepools[1].additional_infra_envs`). */
export function isInfraEnvsPath(path: string): boolean {
  return /^nodepools\[\d+\]\.additional_infra_envs$/.test(path);
}

/** A list of InfraEnv names from a form or file value; anything else is none. */
export function infraEnvNames(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string" && v !== "") : [];
}

/** Why a typed name cannot be added; `null` when it can. */
export function nameProblem(name: string, own: string | undefined, chosen: readonly string[]): string | null {
  if (!DNS_LABEL.test(name)) return "An InfraEnv name is lowercase letters, digits and '-'";
  if (name === own) return "That is the nodepool's own InfraEnv";
  if (chosen.includes(name)) return "Already listed";
  if (chosen.length >= MAX_ADDITIONAL) return `At most ${MAX_ADDITIONAL}`;
  return null;
}

/** The InfraEnvs that may still be added: the MCE's, less the nodepool's own and those listed. */
export function addable(options: readonly string[], own: string | undefined, chosen: readonly string[]): string[] {
  return options.filter((name) => name !== own && !chosen.includes(name));
}

// ── The cluster file (Edit cluster) ─────────────────────────────────────────

/** One agent nodepool of a cluster file, as the InfraEnvs editor shows it. */
export interface FileNodepool {
  index: number;
  /** `infraEnvName`: names the NodePool, never changed here. */
  first: string;
  additional: string[];
  /** Its own `name`, when it sets one. */
  name: string | null;
  /** `upgradeType: Replace`: a change of its InfraEnvs would replace every node. */
  replace: boolean;
}

function load(text: string): Record<string, unknown> | null {
  try {
    const doc = jsYaml.load(text);
    return doc && typeof doc === "object" && !Array.isArray(doc) ? (doc as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** The file's agent nodepools that name an InfraEnv; `null` when it does not parse or is KubeVirt. */
export function fileNodepools(text: string): FileNodepool[] | null {
  const doc = load(text);
  if (!doc || doc.platform === "kubevirt") return null;
  const pools = Array.isArray(doc.nodepool) ? doc.nodepool : [];
  const found: FileNodepool[] = [];
  pools.forEach((pool: unknown, index: number) => {
    if (!pool || typeof pool !== "object" || Array.isArray(pool)) return;
    const entry = pool as Record<string, unknown>;
    if (typeof entry.infraEnvName !== "string" || !entry.infraEnvName) return;
    found.push({
      index,
      first: entry.infraEnvName,
      additional: infraEnvNames(entry[INFRA_ENVS_KEY]),
      name: typeof entry.name === "string" ? entry.name : null,
      replace: entry.upgradeType === "Replace",
    });
  });
  return found;
}

const TOP_KEY = /^[A-Za-z_][\w.-]*:(\s|$)/;
const indentOf = (line: string) => line.length - line.trimStart().length;

/** The `[start, end)` lines of `nodepool[index]`, with its keys' indentation; `null` if not found. */
function itemRange(lines: readonly string[], index: number): { start: number; end: number; keys: number } | null {
  const list = lines.findIndex((l) => /^nodepool:\s*(#.*)?$/.test(l));
  if (list < 0) return null;
  let end = lines.length;
  for (let i = list + 1; i < lines.length; i++) {
    if (TOP_KEY.test(lines[i]) || lines[i].startsWith("# === Added by CI ===")) {
      end = i;
      break;
    }
  }
  const items: number[] = [];
  let dash: number | null = null;
  for (let i = list + 1; i < end; i++) {
    const match = /^(\s*)- /.exec(lines[i]);
    if (match && (dash === null || match[1].length === dash)) {
      dash = match[1].length;
      items.push(i);
    }
  }
  if (dash === null || index >= items.length) return null;
  let stop = index + 1 < items.length ? items[index + 1] : end;
  while (stop > items[index] + 1 && (lines[stop - 1].trim() === "" || lines[stop - 1].trimStart().startsWith("#"))) stop--;
  return { start: items[index], end: stop, keys: dash + 2 };
}

/** The line of `key` in the item, and the lines its value takes; `null` when the item has no `key`. */
function keyLines(lines: readonly string[], range: { start: number; end: number; keys: number }, key: string): [number, number] | null {
  const at = new RegExp(`^(\\s*- )?\\s*${key}:`);
  for (let i = range.start; i < range.end; i++) {
    const own = i === range.start ? true : indentOf(lines[i]) === range.keys;
    if (!own || !at.test(lines[i])) continue;
    let stop = i + 1;
    const inline = lines[i].slice(lines[i].indexOf(`${key}:`) + key.length + 1).replace(/#.*$/, "").trim() !== "";
    if (!inline) {
      while (stop < range.end && (indentOf(lines[stop]) > range.keys || (indentOf(lines[stop]) === range.keys && lines[stop].trimStart().startsWith("- ")))) stop++;
    }
    return [i, stop];
  }
  return null;
}

/**
 * `text` with nodepool `index`'s `additionalInfraEnvNames` set to `names`
 * (removed when empty), every other line byte for byte; written as the shared
 * template writes it, `["a", "b"]`. `null` when the layout is not one this
 * handles: the result must parse and hold exactly the old values with that
 * one change, or nothing is changed and the person edits the text.
 */
export function withInfraEnvs(text: string, index: number, names: readonly string[]): string | null {
  const before = load(text);
  const lines = text.split("\n");
  const range = itemRange(lines, index);
  if (!before || !range) return null;
  const line = `${" ".repeat(range.keys)}${INFRA_ENVS_KEY}: ${JSON.stringify(names).replaceAll(",", ", ")}`;
  const found = keyLines(lines, range, INFRA_ENVS_KEY);
  const next = [...lines];
  if (found) {
    if (found[0] === range.start) return null; // the item's first key: leave it to the person
    next.splice(found[0], found[1] - found[0], ...(names.length > 0 ? [line] : []));
  } else if (names.length > 0) {
    const first = keyLines(lines, range, "infraEnvName");
    if (!first) return null;
    next.splice(first[1], 0, line);
  }
  const result = next.join("\n");
  const after = load(result);
  const expected = structuredClone(before) as Record<string, unknown>;
  const pool = (expected.nodepool as Record<string, unknown>[])[index];
  if (names.length > 0) pool[INFRA_ENVS_KEY] = [...names];
  else delete pool[INFRA_ENVS_KEY];
  return after && JSON.stringify(sorted(after)) === JSON.stringify(sorted(expected)) ? result : null;
}

/** A value with its mappings' keys in order, so two parses compare by content. */
function sorted(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sorted);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((k) => [k, sorted((value as Record<string, unknown>)[k])]));
  }
  return value;
}
