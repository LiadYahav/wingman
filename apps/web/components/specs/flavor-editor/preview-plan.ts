/**
 * The flavor editor's cluster-file preview (`POST /clusters/preview`): the
 * request that renders a saved flavor with the draft's values. Day1 renders
 * only a flavor in the specs repo, at its saved version, and enforces its
 * saved locks (ADR-0026, ADR-0029, ADR-0061) and ratio (ADR-0040).
 */

import { asEntries } from "@/lib/machine-configs";
import { offeredRelease } from "@/lib/release-tags";
import { TUNING, TUNING_RULE, sameTuning, tuningNames, tuningRuleNames } from "@/lib/tuning-profiles";
import { sameValues, type Values } from "@/lib/values";
import type { ClusterSpec, ConfigEntry, CreateClusterRequest, Mce, TemplateField } from "@/types";
import { CONFIGS_RULE, PER_CLUSTER, clone, isLockable, nodepoolCount, nodepoolPath, poolList, type FlavorDraft } from "./model";

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
// eslint-disable-next-line complexity -- size baseline (ADR-0056)
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
    if (path === TUNING_RULE) {
      const ruleSaved = tuningRuleNames(savedValues);
      const pools = poolList(variables);
      if (ruleSaved && !pools.every((p) => sameTuning(tuningNames(p[TUNING]), ruleSaved))) {
        variables.nodepools = pools.map((p) => ({ ...p, [TUNING]: ruleSaved }));
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
  return offeredRelease(preset, offered) ?? offeredRelease(mce?.default_mastertag, offered) ?? offered[0] ?? null;
}
