import { describe, expect, it } from "vitest";
import { ARCHITECTURE_HREF, DIAGRAMS, diagramHref, diagramOf, withTheme } from "./diagrams";

// server-scan's ArchitecturePage.test.tsx cases (92146d3), as its picker's logic.
describe("the diagram picker", () => {
  it("defaults to the full-flow diagram", () => {
    expect(diagramOf(null)).toEqual(DIAGRAMS[0]);
    expect(DIAGRAMS[0]).toMatchObject({ slug: "runtime-architecture", label: "Full flow" });
  });

  it("selects the diagram named in the URL", () => {
    expect(diagramOf("oneview").label).toBe("HPE OneView");
  });

  it("falls back to the first for a name it does not list", () => {
    expect(diagramOf("gone")).toEqual(DIAGRAMS[0]);
  });

  it("puts the diagram in the URL, but not the first", () => {
    expect(diagramHref("ucs-central")).toBe(`${ARCHITECTURE_HREF}?diagram=ucs-central`);
    expect(diagramHref("runtime-architecture")).toBe(ARCHITECTURE_HREF);
    expect(ARCHITECTURE_HREF).toBe("/server-scan/architecture");
  });

  it("lists server-scan's seven diagrams, each name once", () => {
    const slugs = DIAGRAMS.map((d) => d.slug);
    expect(slugs).toEqual([
      "runtime-architecture",
      "ucs-central",
      "intersight",
      "openmanage",
      "oneview",
      "redfish-standalone",
      "nodes-status",
    ]);
    expect(new Set(slugs).size).toBe(slugs.length);
  });
});

/** The script `withTheme` adds, run against a `window` whose browser prefers `browser`. */
function themed(html: string, browser: "light" | "dark") {
  const script = /<script>([\s\S]*?)<\/script>/.exec(html)?.[1] ?? "";
  const matchMedia = (query: string) => ({
    media: query,
    matches: query === "all" || (query !== "not all" && query.includes(`prefers-color-scheme: ${browser}`)),
  });
  const window = { matchMedia };
  new Function("window", script)(window);
  return window.matchMedia;
}

describe("telling a diagram Wingman's theme", () => {
  const page = '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n</head><body></body></html>';

  it("goes first in the head, before the diagram's own scripts read the preference", () => {
    const html = withTheme(page, "dark");
    expect(html.indexOf("<script>")).toBe(html.indexOf("<head>") + "<head>".length);
    expect(html.replace(/<script>[\s\S]*?<\/script>/, "")).toBe(page);
  });

  it("answers the colour preference with Wingman's theme, whatever the browser prefers", () => {
    const dark = themed(withTheme(page, "dark"), "light");
    expect(dark("(prefers-color-scheme: light)").matches).toBe(false);
    expect(dark("(prefers-color-scheme: dark)").matches).toBe(true);
    const light = themed(withTheme(page, "light"), "dark");
    expect(light("(prefers-color-scheme: light)").matches).toBe(true);
  });

  it("leaves every other query to the browser", () => {
    const query = themed(withTheme(page, "dark"), "light");
    expect(query("(prefers-reduced-motion: reduce)").media).toBe("(prefers-reduced-motion: reduce)");
  });

  it("finds a head with attributes, and goes first in a page without one", () => {
    expect(withTheme('<html><head lang="en"><title>x</title></head></html>', "light")).toMatch(/^<html><head lang="en"><script>/);
    expect(withTheme("<svg></svg>", "light")).toMatch(/^<script>.*<\/script><svg><\/svg>$/);
    expect(withTheme("<header></header>", "light")).toMatch(/^<script>/);
  });
});
