/**
 * A page that scrolls inside a box of its own (server-scan v6.4.0 and v6.6.0;
 * ADR-0048's v6.6.0 amendment): the Servers and Events tables.
 */

import type { Page } from "@playwright/test";

/**
 * How the page and a scroll box stand: `main` is the shell's scroll container,
 * `box` the table's own; `pinned` is whether the header sits at the box's top.
 */
export async function scrollState(page: Page, box: string) {
  return page.evaluate((selector) => {
    const main = document.querySelector("main") as HTMLElement;
    const el = document.querySelector(selector) as HTMLElement;
    const head = el.querySelector("thead") as HTMLElement;
    return {
      pageScrolls: main.scrollHeight > main.clientHeight + 1,
      mainTop: main.scrollTop,
      boxScrolls: el.scrollHeight > el.clientHeight,
      boxTop: el.scrollTop,
      pinned: Math.abs(head.getBoundingClientRect().top - el.getBoundingClientRect().top) <= 1,
    };
  }, box);
}
