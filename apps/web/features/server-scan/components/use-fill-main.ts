"use client";

// What it follows upstream, and at which version: docs/integrations/server-scan.yaml.

import { useLayoutEffect, useState, type CSSProperties } from "react";
import { FILL_MIN_HEIGHT, fillHeight } from "@/features/server-scan/lib/fill";

/** The custom property a box's `max-h-[var(--ss-fill,…)]` reads. */
const FILL_VAR = "--ss-fill";

/**
 * Caps a box so its page never scrolls (server-scan's `useFillViewport`,
 * `lib/fill.ts`): the shell's `main` height less the box's top and what must
 * stay under it, the rest of its column (`column: true`, a pager) and the
 * bottom padding of the page (`[data-fill-page]`). Measured from layout,
 * never from the scroll position, on mount, when `dep` changes (the row
 * count), on resize and when the column's size changes.
 *
 * Returns `attach`, the box's callback ref, and the style that sets `--ss-fill` on it.
 */
export function useFillMain<T extends HTMLElement>(dep: unknown, { column = true, min = FILL_MIN_HEIGHT } = {}) {
  const [box, setBox] = useState<T | null>(null);
  const [height, setHeight] = useState<number | undefined>(undefined);
  useLayoutEffect(() => {
    const main = box?.closest("main");
    if (!box || !main) return;
    const parent = box.parentElement;
    const update = () => {
      const rect = box.getBoundingClientRect();
      const page = box.closest<HTMLElement>("[data-fill-page]");
      const under =
        (column && parent ? parent.getBoundingClientRect().bottom - rect.bottom : 0) +
        (page ? parseFloat(getComputedStyle(page).paddingBottom) : 0);
      const top = rect.top - main.getBoundingClientRect().top + main.scrollTop;
      setHeight(fillHeight({ main: main.clientHeight, top, under }, min));
    };
    update();
    window.addEventListener("resize", update);
    const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(update);
    if (parent) observer?.observe(parent);
    return () => {
      window.removeEventListener("resize", update);
      observer?.disconnect();
    };
  }, [box, dep, column, min]);
  const style = height === undefined ? undefined : ({ [FILL_VAR]: `${height}px` } as CSSProperties);
  return { attach: setBox, style };
}
