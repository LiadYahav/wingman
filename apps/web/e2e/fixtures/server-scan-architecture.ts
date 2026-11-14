/**
 * Architecture page mocks (docs/notes/2026-11-13-server-scan-area-api.md §11):
 * day1's answer for one of server-scan's diagrams, the page as its UI serves
 * it. Each made-up page names its diagram and says which colour scheme its
 * scripts see, and whether they can reach Wingman's page, as a diagram's
 * own scripts would try.
 */

import type { Page, Route } from "@playwright/test";
import { json } from "./api-handlers";
import { setUpServerScan } from "./server-scan";
import type { DiagramAnswer } from "../../types/server-scan-architecture";

/** A stand-in for one of server-scan's archify pages. */
export function diagramPage(slug: string): string {
  return `<!DOCTYPE html>
<html lang="en"><head><meta name="generator" content="archify 2.16.0-dev.0"><title>${slug} Diagram</title></head>
<body><h1>Diagram ${slug}</h1><p id="theme"></p><p id="reach"></p>
<script>
document.getElementById("theme").textContent = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
var reach;
try { reach = parent.document.title ? "reached Wingman" : "reached Wingman"; } catch (e) { reach = "kept out"; }
try { localStorage.getItem("x"); reach += ", storage open"; } catch (e) { reach += ", no storage"; }
document.getElementById("reach").textContent = reach;
</script></body></html>`;
}

type Handler = (route: Route, slug: string) => Promise<void> | void;

const answer: Handler = (route, slug) => json(route, { slug, html: diagramPage(slug) } satisfies DiagramAnswer);

/**
 * Sign in as an admin with the area on (or `viewer`), and answer every
 * diagram with `diagram`. Returns the diagrams asked for, in order.
 */
export async function setUpArchitecture(
  page: Page,
  { diagram = answer, viewer = false }: { diagram?: Handler; viewer?: boolean } = {}
): Promise<{ asked: string[] }> {
  const asked: string[] = [];
  await setUpServerScan(page, { viewer });
  await page.route("**/api/day1/server-scan/architecture/*", (route) => {
    const slug = new URL(route.request().url()).pathname.split("/").pop() ?? "";
    asked.push(slug);
    return diagram(route, slug);
  });
  return { asked };
}
