/**
 * The desktop sidebar's icon rail: whether it is collapsed is a per-browser
 * preference in localStorage (expanded unless chosen), applied before the
 * first paint by `SIDEBAR_SCRIPT` as an attribute on `<html>` that the CSS
 * reads (globals.css: `--app-sidebar-width` and the `rail:` variant), so a
 * page never paints at the wrong width and then jumps.
 */

import { isTyping } from "./keyboard";

/** The localStorage key, and the value that means the rail. */
export const SIDEBAR_STORAGE_KEY = "wingman-sidebar";
const COLLAPSED = "collapsed";
const EXPANDED = "expanded";

/** Present on `<html>` while the desktop sidebar is a rail. */
export const COLLAPSED_ATTRIBUTE = "data-sidebar-collapsed";

/** The stored choice: true for the rail; false when expanded, never chosen, or storage is unavailable. */
export function readCollapsed(storage: Pick<Storage, "getItem"> | undefined): boolean {
  try {
    return storage?.getItem(SIDEBAR_STORAGE_KEY) === COLLAPSED;
  } catch {
    return false;
  }
}

/** Keeps the choice for the next visit; false when storage is unavailable (it then lasts for this page). */
export function writeCollapsed(storage: Pick<Storage, "setItem"> | undefined, collapsed: boolean): boolean {
  try {
    if (!storage) return false;
    storage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? COLLAPSED : EXPANDED);
    return true;
  } catch {
    return false;
  }
}

/**
 * Runs in `<head>` while the HTML is parsed, before the first paint and before
 * React: the same read as `readCollapsed`, setting `COLLAPSED_ATTRIBUTE`.
 */
export const SIDEBAR_SCRIPT =
  `try{if(localStorage.getItem(${JSON.stringify(SIDEBAR_STORAGE_KEY)})===${JSON.stringify(COLLAPSED)})` +
  `document.documentElement.setAttribute(${JSON.stringify(COLLAPSED_ATTRIBUTE)},"")}catch(e){}`;

type ShortcutEvent = Pick<KeyboardEvent, "key" | "code" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey" | "repeat" | "target">;

/**
 * Ctrl+B or ⌘B, not held down and not while typing in a field. The B is the
 * key's letter, or the B key's position when the layout's letter is not
 * Latin (a Hebrew layout gives "נ" there).
 */
export function isSidebarShortcut(event: ShortcutEvent): boolean {
  if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || event.repeat) return false;
  const isB = /^[a-z]$/i.test(event.key) ? event.key.toLowerCase() === "b" : event.code === "KeyB";
  return isB && !isTyping(event.target);
}

/** The shortcut as this platform writes it: ⌘B on Apple's, Ctrl+B elsewhere. */
export function sidebarShortcutLabel(platform: string): string {
  return /Mac|iPhone|iPad|iPod/.test(platform) ? "⌘B" : "Ctrl+B";
}
