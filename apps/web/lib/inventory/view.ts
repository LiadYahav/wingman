/**
 * Which MCE Inventory Management shows, and the InfraEnvs picked on it
 * (ADR-0057's 2026-11-24 amendment). Both are in the URL,
 * `?mce=<name>&infraEnv=<a>,<b>`, so a link opens one MCE and a reload keeps
 * the view; and both are kept per viewer in localStorage for the next visit,
 * read and written in try/catch (with storage blocked the URL still holds
 * them). The InfraEnvs are names, not one MCE's: the platform names a pool by
 * flavor, size and zone, with no hub and no site, so every hub at a site has
 * the same ones, and a change of MCE keeps them.
 */

import type { MceInventory } from "@/types/inventory";
import { firstWithPools } from "./pools";

const MCE_PARAM = "mce";
const INFRA_ENV_PARAM = "infraEnv";

/** The localStorage key: `{"mce": <name> | null, "infraEnvs": [<name>, …]}`. */
const VIEW_KEY = "wingman-inventory-view";

/** More names than any MCE has pools: a bound on what a URL or storage can make the page hold. */
const MAX_NAMES = 200;

export interface InventoryView {
  mce: string | null;
  /** The InfraEnvs picked, by name, in name order; none: every pool. */
  infraEnvs: string[];
}

/** What the URL says; each part `null` when it says nothing of it. */
export interface UrlView {
  mce: string | null;
  infraEnvs: string[] | null;
}

/** Each name once, trimmed, in name order, at most `MAX_NAMES`. */
export function cleanNames(names: readonly unknown[]): string[] {
  const kept = names.flatMap((name) => (typeof name === "string" && name.trim() ? [name.trim()] : []));
  return [...new Set(kept)].sort().slice(0, MAX_NAMES);
}

/** The view a URL's query names: `infraEnv` comma-separated or repeated; an empty one is "every pool". */
export function viewFromSearch(search: string): UrlView {
  const params = new URLSearchParams(search);
  const infraEnvs = params.getAll(INFRA_ENV_PARAM);
  return {
    mce: params.get(MCE_PARAM)?.trim() || null,
    infraEnvs: infraEnvs.length > 0 ? cleanNames(infraEnvs.flatMap((value) => value.split(","))) : null,
  };
}

/** The URL showing `view`, every other part of `url` kept. */
export function withView(url: { pathname: string; search: string; hash: string }, view: InventoryView): string {
  const params = new URLSearchParams(url.search);
  if (view.mce) params.set(MCE_PARAM, view.mce);
  else params.delete(MCE_PARAM);
  if (view.infraEnvs.length > 0) params.set(INFRA_ENV_PARAM, view.infraEnvs.join(","));
  else params.delete(INFRA_ENV_PARAM);
  const query = params.toString().replaceAll("%2C", ",");
  return `${url.pathname}${query ? `?${query}` : ""}${url.hash}`;
}

/** Inventory Management opened on `mce`, for the pages that link to one MCE's pools. */
export const inventoryHref = (mce: string): string => `/inventory?${new URLSearchParams({ [MCE_PARAM]: mce })}`;

const NOTHING_STORED: InventoryView = { mce: null, infraEnvs: [] };

/** The view a stored value names; nothing for no value or one of another shape. */
export function parseStoredView(raw: string | null): InventoryView {
  if (!raw) return NOTHING_STORED;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return NOTHING_STORED;
    const { mce, infraEnvs } = value as Record<string, unknown>;
    return { mce: typeof mce === "string" && mce ? mce : null, infraEnvs: Array.isArray(infraEnvs) ? cleanNames(infraEnvs) : [] };
  } catch {
    return NOTHING_STORED;
  }
}

export const serializeView = (view: InventoryView): string => JSON.stringify({ mce: view.mce, infraEnvs: view.infraEnvs });

/** The stored value; `null` when there is none or storage is unavailable. */
export function readStoredView(storage: Pick<Storage, "getItem"> | undefined): string | null {
  try {
    return storage?.getItem(VIEW_KEY) ?? null;
  } catch {
    return null;
  }
}

/** Keeps `value` for the next visit; `false` when storage is unavailable. */
export function writeStoredView(storage: Pick<Storage, "setItem"> | undefined, value: string): boolean {
  try {
    if (!storage) return false;
    storage.setItem(VIEW_KEY, value);
    return true;
  } catch {
    return false;
  }
}

export interface ResolvedView {
  /** `null` only when day1 names no MCE. */
  mce: MceInventory | null;
  infraEnvs: string[];
  /** The URL's MCE when day1 has none of that name: the page says so and shows the default. */
  unknownMce: string | null;
}

/**
 * The view to show: the URL's MCE, else the remembered one, else the first
 * with something to show (an unknown URL MCE falls back to that, said); the
 * URL's InfraEnvs, else the remembered ones. Each part is taken on its own, so
 * a link to one MCE keeps the viewer's InfraEnvs.
 */
export function resolveView(url: UrlView, stored: InventoryView, mces: readonly MceInventory[]): ResolvedView {
  const named = (name: string | null) => (name ? mces.find((mce) => mce.mce === name) : undefined);
  const fromUrl = named(url.mce);
  const unknownMce = url.mce && !fromUrl ? url.mce : null;
  const mce = fromUrl ?? (unknownMce ? undefined : named(stored.mce)) ?? firstWithPools(mces);
  return { mce: mce ?? null, infraEnvs: url.infraEnvs ?? stored.infraEnvs, unknownMce };
}
