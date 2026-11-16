/**
 * Which MCE cards a person collapsed on Inventory Management (ADR-0057's
 * 3.38.0 amendment): a per-viewer convenience in localStorage, every card
 * expanded unless chosen. Read and written in try/catch, so with storage
 * blocked or holding something else every card is expanded, and a choice
 * made then lasts for the page.
 */

/** The localStorage key: a JSON list of the collapsed MCEs' names. */
const COLLAPSED_MCES_KEY = "wingman-inventory-collapsed";

const NONE: ReadonlySet<string> = new Set();

/** The collapsed MCEs a stored value names; nothing for no value or one of another shape. */
export function parseCollapsed(raw: string | null): ReadonlySet<string> {
  if (!raw) return NONE;
  try {
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value)) return NONE;
    return new Set(value.filter((name): name is string => typeof name === "string"));
  } catch {
    return NONE;
  }
}

/** The value to store for these MCEs, in name order. */
export const serializeCollapsed = (collapsed: ReadonlySet<string>): string => JSON.stringify([...collapsed].sort());

/** `collapsed` with `mce` collapsed or expanded again. */
export function toggledMce(collapsed: ReadonlySet<string>, mce: string): Set<string> {
  const next = new Set(collapsed);
  if (next.has(mce)) next.delete(mce);
  else next.add(mce);
  return next;
}

/** The stored value; `null` when there is none or storage is unavailable. */
export function readCollapsedMces(storage: Pick<Storage, "getItem"> | undefined): string | null {
  try {
    return storage?.getItem(COLLAPSED_MCES_KEY) ?? null;
  } catch {
    return null;
  }
}

/** Keeps `value` for the next visit; `false` when storage is unavailable. */
export function writeCollapsedMces(storage: Pick<Storage, "setItem"> | undefined, value: string): boolean {
  try {
    if (!storage) return false;
    storage.setItem(COLLAPSED_MCES_KEY, value);
    return true;
  } catch {
    return false;
  }
}
