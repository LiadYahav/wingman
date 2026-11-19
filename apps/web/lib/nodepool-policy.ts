/**
 * A nodepool's own scale-down policy (ADR-0062): which servers leave first
 * when its NodePool scales down. update-nodepool reads it off the NodePool's
 * `redbull.io/scale-down-policy` annotation, which the hostedclusters-setup
 * chart renders from the `nodepool[]` entry's `annotations`. Day1 writes it
 * at create from the template input `nodepools[].scale_down_policy`, offered
 * in the template schema only when the specs project's template reads it, so
 * the schema is the one switch the web reads. None is the platform default:
 * nothing is written, and CAPI picks at random.
 */

import type { TemplateField } from "@/types";
import { indentOf, itemRange, keyLines, load, sorted } from "@/lib/infra-envs";

export const POLICY_INPUT = "scale_down_policy";
const POLICY_KEY = "redbull.io/scale-down-policy";
const ANNOTATIONS = "annotations";

/** The policies update-nodepool knows, each in one line; it refuses any other. */
export const POLICIES = [
  { value: "fewest-pods", note: "The nodes running the fewest workload pods leave first: the least for the drain to move." },
  { value: "least-requested", note: "The nodes whose pods request the least CPU or memory leave first." },
  { value: "least-utilized", note: "The nodes using the least CPU or memory now leave first; needs the hosted cluster's metrics API." },
] as const;

/** What the platform default does. */
const DEFAULT_NOTE = "Nothing written: CAPI picks the nodes that leave at random.";

/** Whether day1 offers the input: its template schema lists it under `nodepools`. */
export function offersPolicy(schema: readonly TemplateField[] | undefined): boolean {
  const nodepools = schema?.find((f) => f.name === "nodepools");
  return Boolean(nodepools?.fields?.some((f) => f.name === POLICY_INPUT));
}

/** Whether `path` is a nodepool's policy input (`nodepools[1].scale_down_policy`). */
export const isPolicyPath = (path: string): boolean => /^nodepools\[\d+\]\.scale_down_policy$/.test(path);

/** A form or file value as a policy: its text, `null` for none (left out or empty). */
export const policyOf = (value: unknown): string | null => (typeof value === "string" && value !== "" ? value : null);

/** The line a policy is explained by; an unknown one is the workflow's to refuse. */
export function policyNote(policy: string | null): string {
  if (policy === null) return DEFAULT_NOTE;
  return POLICIES.find((p) => p.value === policy)?.note ?? `update-nodepool does not know “${policy}” and refuses it at the next scale-down.`;
}

/** A nodepool input without an empty policy: the platform default is no key at all. */
export function withoutDefaultPolicy<T extends Record<string, unknown>>(pool: T): T {
  if (!(POLICY_INPUT in pool) || policyOf(pool[POLICY_INPUT]) !== null) return pool;
  const rest = { ...pool };
  delete rest[POLICY_INPUT];
  return rest;
}

// ── The cluster file (Edit cluster) ─────────────────────────────────────────

/** One nodepool entry of a cluster file, as the policy editor shows it. */
export interface FilePolicy {
  index: number;
  /** Its `name`, else its `infraEnvName`, else its position. */
  label: string;
  policy: string | null;
}

/** Each nodepool entry and its policy annotation; `null` when the file does not parse. */
export function filePolicies(text: string): FilePolicy[] | null {
  const doc = load(text);
  if (!doc) return null;
  const pools = Array.isArray(doc.nodepool) ? doc.nodepool : [];
  return pools.flatMap((pool: unknown, index: number) => {
    if (!pool || typeof pool !== "object" || Array.isArray(pool)) return [];
    const entry = pool as Record<string, unknown>;
    const label = [entry.name, entry.infraEnvName].find((v): v is string => typeof v === "string" && v !== "") ?? `nodepool[${index}]`;
    const annotations = entry[ANNOTATIONS];
    const policy = annotations && typeof annotations === "object" ? policyOf((annotations as Record<string, unknown>)[POLICY_KEY]) : null;
    return [{ index, label, policy }];
  });
}

const POLICY_LINE = /^(\s*)redbull\.io\/scale-down-policy:[^#]*?(\s+#.*)?$/;

/** The lines a new or changed policy takes, or `null` when the entry's layout is not one this edits. */
function edited(lines: readonly string[], index: number, policy: string | null): string[] | null {
  const range = itemRange(lines, index);
  if (!range) return null;
  const pad = " ".repeat(range.keys);
  const found = keyLines(lines, range, ANNOTATIONS);
  const next = [...lines];
  if (!found) {
    if (policy !== null) next.splice(range.end, 0, `${pad}${ANNOTATIONS}:`, `${pad}  ${POLICY_KEY}: ${policy}`);
    return next;
  }
  const [head, stop] = found;
  if (head === range.start || lines[head].replace(/#.*$/, "").trim() !== `${ANNOTATIONS}:`) return null; // inline, or the item's first key
  const children = lines.slice(head + 1, stop);
  const at = children.findIndex((l) => POLICY_LINE.test(l));
  if (at >= 0 && policy !== null) {
    const [, lead, comment] = POLICY_LINE.exec(children[at]) ?? [];
    next[head + 1 + at] = `${lead}${POLICY_KEY}: ${policy}${comment ?? ""}`;
  } else if (at >= 0) {
    const others = children.filter((l, i) => i !== at && l.trim() !== "" && !l.trimStart().startsWith("#"));
    if (others.length === 0) next.splice(head, stop - head);
    else next.splice(head + 1 + at, 1);
  } else if (policy !== null) {
    const content = children.find((l) => l.trim() !== "" && !l.trimStart().startsWith("#"));
    next.splice(stop, 0, `${" ".repeat(content ? indentOf(content) : range.keys + 2)}${POLICY_KEY}: ${policy}`);
  }
  return next;
}

/**
 * `text` with nodepool `index`'s policy annotation set to `policy` (removed,
 * with an `annotations` block left empty, for `null`), every other line byte
 * for byte, written as the shared template writes it. `null` when the layout
 * is not one this handles (a flow-style `annotations`, a quoted key): the
 * result must parse and hold exactly the old values with that one change, or
 * nothing is changed and the person edits the text.
 */
export function withPolicy(text: string, index: number, policy: string | null): string | null {
  const before = load(text);
  const next = before ? edited(text.split("\n"), index, policy) : null;
  if (!before || !next) return null;
  const result = next.join("\n");
  const expected = structuredClone(before) as Record<string, unknown>;
  const pool = (expected.nodepool as Record<string, unknown>[])[index];
  const annotations = { ...((pool[ANNOTATIONS] as Record<string, unknown> | null) ?? {}) };
  if (policy === null) delete annotations[POLICY_KEY];
  else annotations[POLICY_KEY] = policy;
  if (Object.keys(annotations).length > 0) pool[ANNOTATIONS] = annotations;
  else delete pool[ANNOTATIONS];
  const after = load(result);
  return after && JSON.stringify(sorted(after)) === JSON.stringify(sorted(expected)) ? result : null;
}
