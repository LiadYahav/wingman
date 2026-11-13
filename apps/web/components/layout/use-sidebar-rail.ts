"use client";

import { createContext, use, useCallback, useEffect, useLayoutEffect, useMemo, useSyncExternalStore } from "react";
import { COLLAPSED_ATTRIBUTE, isSidebarShortcut, readCollapsed, writeCollapsed } from "@/lib/sidebar-rail";

/** Fired on this page when the sidebar collapses or expands. */
const CHANGE_EVENT = "wingman:sidebar";

export interface SidebarRail {
  /** This copy of the sidebar is the desktop's, shown as an icon rail. */
  collapsed: boolean;
  toggle: () => void;
}

/**
 * Every area's sidebar reads this (one state for all of them). The desktop
 * copy gets `useSidebarRailState`'s value; the mobile sheet keeps the default,
 * so it is never a rail.
 */
export const SidebarRailContext = createContext<SidebarRail>({ collapsed: false, toggle: () => {} });

export const useSidebarRail = (): SidebarRail => use(SidebarRailContext);

const browserStorage = (): Storage | undefined => {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => window.removeEventListener(CHANGE_EVENT, onChange);
}

/**
 * The page's state is the attribute on `<html>`: set before the first paint
 * from storage (`SIDEBAR_SCRIPT`), read by the CSS, changed only by `apply`.
 * So the layout never waits for React, and with storage blocked the choice
 * still holds for the page.
 */
const isCollapsed = () => document.documentElement.hasAttribute(COLLAPSED_ATTRIBUTE);

function apply(collapsed: boolean) {
  document.documentElement.toggleAttribute(COLLAPSED_ATTRIBUTE, collapsed);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/**
 * The desktop sidebar's collapsed state, its toggle, and Ctrl+B / ⌘B (never
 * while typing in a field). Call it once, in the shell. The server and the
 * hydration pass render it expanded; the CSS already shows the rail by then,
 * and only the toggle's label and the tooltips wait for React.
 */
export function useSidebarRailState(): SidebarRail {
  const collapsed = useSyncExternalStore(subscribe, isCollapsed, () => false);

  const toggle = useCallback(() => {
    const next = !isCollapsed();
    writeCollapsed(browserStorage(), next);
    apply(next);
  }, []);

  // React's Strict Mode remount (development only) resets <html>'s attributes: put the stored choice back.
  useLayoutEffect(() => {
    if (readCollapsed(browserStorage()) && !isCollapsed()) apply(true);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!isSidebarShortcut(event)) return;
      event.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  return useMemo(() => ({ collapsed, toggle }), [collapsed, toggle]);
}
