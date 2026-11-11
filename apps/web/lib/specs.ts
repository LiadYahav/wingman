/**
 * Helpers the spec pages share: the rules the day1 service checks a spec
 * against (domain/specs.py) and the exact document a spec write sends.
 */

import type { ClusterSpec } from "@/types";

const SPEC_NAME = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;
const SPEC_VERSION = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$/;
const MAX_NAME = 63;

/**
 * `/api/day1/specs/{name}`; for a write, guarded by the `last_commit_id` the
 * spec was read at, when the read gave one (ADR-0006).
 */
export function specApiPath(name: string, lastCommitId?: string | null): string {
  const path = `/api/day1/specs/${encodeURIComponent(name)}`;
  return lastCommitId ? `${path}?last_commit_id=${encodeURIComponent(lastCommitId)}` : path;
}

/** Why a spec name would be refused (a DNS-1123 label); `null` when it is fine. */
export function specNameProblem(name: string): string | null {
  if (!name) return "A spec name is required";
  if (name.length > MAX_NAME) return `At most ${MAX_NAME} characters (${name.length} now)`;
  if (!SPEC_NAME.test(name)) {
    return "Lowercase letters, digits and '-', starting and ending with a letter or digit";
  }
  return null;
}

/** Why a spec version would be refused (one word, like 1.2.0); `null` when it is fine. */
export function specVersionProblem(version: string): string | null {
  if (!version) return "A version is required";
  if (!SPEC_VERSION.test(version)) {
    return "One word of letters, digits, '.', '_', '+' or '-', like 1.2.0";
  }
  return null;
}

/**
 * The document a spec write sends. Request bodies refuse unknown fields, so
 * a read's extras (`load_error`, `load_problems`) never go back, and the
 * shared template (filled on read, never stored) is sent empty.
 */
export function specDocument(spec: ClusterSpec): ClusterSpec {
  const { day1, day2 } = spec.spec;
  return {
    apiVersion: spec.apiVersion,
    kind: spec.kind,
    metadata: {
      name: spec.metadata.name,
      description: spec.metadata.description ?? "",
      version: spec.metadata.version,
      labels: spec.metadata.labels ?? {},
    },
    spec: {
      day1: {
        variables: day1.variables ?? [],
        structure: day1.structure ?? {},
        locked_paths: day1.locked_paths ?? [],
        template: "",
        values: day1.values ?? {},
        ...(day1.nodepool_ratio?.length ? { nodepool_ratio: day1.nodepool_ratio } : {}),
      },
      day2: { addons: day2.addons ?? [] },
    },
  };
}

/** `nodepools: [{}, {}]` → `["2 nodepools"]`, `[{}]` → `["1 nodepool"]`: the list counts every cluster of the flavor gets. */
export function structureSummary(structure: Record<string, unknown> | undefined): string[] {
  return Object.entries(structure ?? {})
    .filter(([, value]) => Array.isArray(value))
    .map(([key, value]) => {
      const count = (value as unknown[]).length;
      const noun = key.replace(/_/g, " ");
      return `${count} ${count === 1 ? noun.replace(/s$/, "") : noun}`;
    });
}

/** A preset value as one line: scalars as is, lists and maps as compact JSON. */
export function formatPreset(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
