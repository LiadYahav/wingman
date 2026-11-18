/**
 * A flavor's image mirrors (ADR-0063): two optional top-level template
 * inputs, each a preset or locked as a whole.
 *
 * - `image_content_sources`: the cluster's own mirrors, `{source, mirrors}`
 *   each, which the template writes to the cluster file's
 *   `imageContentSources`. The hostedclusters-setup chart merges them with
 *   the MCE's `defaultImageContentSources` (one source's mirrors unioned).
 * - `disable_idms_merge: true` writes `disableIdmsMerge: true`: the cluster
 *   then uses only its own mirrors, and the MCE's defaults are dropped.
 *
 * Absent, nothing is written and the MCE's default mirrors apply, as before
 * mirrors existed. Day1 is the authority: these checks only answer sooner.
 */

import { isMapping } from "@/lib/values";

export const IMAGE_MIRRORS = "image_content_sources";
export const DROP_MCE_MIRRORS = "disable_idms_merge";
export const MIRROR_INPUTS: readonly string[] = [IMAGE_MIRRORS, DROP_MCE_MIRRORS];

export const isMirrorInput = (path: string) => MIRROR_INPUTS.includes(path);

export interface MirrorEntry {
  source: string;
  mirrors: string[];
}

/** A value as entries, keeping the ones being typed (an empty source or mirror); anything else is dropped. */
export function asMirrorEntries(value: unknown): MirrorEntry[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isMapping).map((entry) => ({
    source: typeof entry.source === "string" ? entry.source : "",
    mirrors: Array.isArray(entry.mirrors) ? entry.mirrors.filter((m): m is string => typeof m === "string") : [],
  }));
}

/** Whether the MCE's default mirrors are dropped: only a JSON `true` does it. */
export const dropsMceMirrors = (value: unknown) => value === true;

/** `source → m1, m2`: one entry in one line, for summaries. */
function mirrorLine(entry: MirrorEntry): string {
  return `${entry.source || "—"} → ${entry.mirrors.length > 0 ? entry.mirrors.join(", ") : "no mirrors"}`;
}

/** A mirror entry as a file or a flavor holds it, in one line; `null` for anything that is not one. */
export function mirrorEntryText(value: unknown): string | null {
  if (!isMapping(value) || typeof value.source !== "string") return null;
  return mirrorLine(asMirrorEntries([value])[0]);
}

/** A list of mirror entries as one line (`a → m1; b → m2`); `null` for any other value. */
export function mirrorListText(value: unknown): string | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const lines = value.map(mirrorEntryText);
  return lines.every((line) => line !== null) ? lines.join("; ") : null;
}

/** A mirror input's value as a summary line: the entries, or the MCE defaults kept or dropped. */
export function mirrorValueText(input: string, value: unknown): string {
  if (input === DROP_MCE_MIRRORS) {
    return dropsMceMirrors(value) ? "Dropped: only the cluster's own mirrors" : "Kept: merged with the cluster's own";
  }
  const entries = asMirrorEntries(value);
  return entries.length === 0 ? "None of its own" : entries.map(mirrorLine).join("; ");
}

/** What a summary calls the two inputs. */
export function mirrorLabel(input: string): string {
  return input === DROP_MCE_MIRRORS ? "MCE default mirrors" : "Image mirrors";
}

// ── Day1's rules, mirrored ──────────────────────────────────────────────────

const MAX_TEXT = 253;

/** Day1's safe-value rule (ADR-0013): no quote, backslash or control character. */
const unsafe = (text: string) =>
  [...text].some((c) => c === '"' || c === "\\" || c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127);

function textProblem(text: string, what: string): string | null {
  if (!text) return `Give the ${what}`;
  if (/\s/.test(text)) return `The ${what} has a space in it`;
  if (unsafe(text)) return `The ${what} may not hold a quote, a backslash or a control character`;
  if (text.length > MAX_TEXT) return `The ${what} is longer than ${MAX_TEXT} characters`;
  return null;
}

export interface MirrorProblem {
  /** The entry it is about; `null` for the whole list. */
  entry: number | null;
  /** The mirror it is about, within the entry. */
  mirror?: number;
  message: string;
}

/** Why day1 would refuse these entries, each at its entry (and mirror). */
export function mirrorEntryProblems(entries: MirrorEntry[]): MirrorProblem[] {
  const problems: MirrorProblem[] = [];
  const firstOf = new Map<string, number>();
  entries.forEach((entry, i) => {
    const source = textProblem(entry.source, "source");
    if (source) problems.push({ entry: i, message: source });
    const earlier = firstOf.get(entry.source);
    if (entry.source && earlier !== undefined) {
      problems.push({ entry: i, message: `${entry.source} is listed twice (entry ${earlier + 1}): give all its mirrors in one entry` });
    } else if (entry.source) firstOf.set(entry.source, i);
    if (entry.mirrors.length === 0) problems.push({ entry: i, message: "Give at least one mirror" });
    entry.mirrors.forEach((mirror, j) => {
      const text = textProblem(mirror, "mirror");
      if (text) problems.push({ entry: i, mirror: j, message: text });
      else if (entry.mirrors.indexOf(mirror) < j) problems.push({ entry: i, mirror: j, message: `${mirror} is listed twice` });
    });
  });
  return problems;
}

/** The problem of dropping the MCE's mirrors without any of the cluster's own; `null` when there is none. */
export function noMirrorsProblem(values: Record<string, unknown>): string | null {
  if (!dropsMceMirrors(values[DROP_MCE_MIRRORS])) return null;
  if (asMirrorEntries(values[IMAGE_MIRRORS]).length > 0) return null;
  return "The cluster would have no image mirrors: add its own, or keep the MCE's default mirrors";
}

/** A problem at its field, as the flavor editor counts them (`entry` is a config list's; never set here). */
export interface MirrorIssue {
  path: string;
  message: string;
  entry?: number;
}

/** Every problem day1 would refuse the two inputs with, at their field. */
export function mirrorIssues(values: Record<string, unknown>): MirrorIssue[] {
  const issues: MirrorIssue[] = [];
  const list = values[IMAGE_MIRRORS];
  if (list !== undefined && !Array.isArray(list)) issues.push({ path: IMAGE_MIRRORS, message: "A list of mirror entries" });
  for (const p of mirrorEntryProblems(asMirrorEntries(list))) {
    issues.push({ path: IMAGE_MIRRORS, message: `Entry ${(p.entry ?? 0) + 1}: ${p.message}` });
  }
  const drop = values[DROP_MCE_MIRRORS];
  if (drop !== undefined && typeof drop !== "boolean") issues.push({ path: DROP_MCE_MIRRORS, message: "On or off (true or false)" });
  const none = noMirrorsProblem(values);
  if (none) issues.push({ path: DROP_MCE_MIRRORS, message: none });
  return issues;
}

/** Day1's `[0].source: ...` (a problem under the list, as the editor shows it) in words: `Entry 1, source: ...`. */
export function readableMirrorProblem(problem: string): string {
  return problem
    .replace(/^\[(\d+)\]\.mirrors\[(\d+)\]: /, (_, e, m) => `Entry ${Number(e) + 1}, mirror ${Number(m) + 1}: `)
    .replace(/^\[(\d+)\]\.(source|mirrors): /, (_, e, part) => `Entry ${Number(e) + 1}, ${part}: `)
    .replace(/^\[(\d+)\]: /, (_, e) => `Entry ${Number(e) + 1}: `);
}
