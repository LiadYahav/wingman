import { describe, expect, it } from "vitest";
import type { Platform } from "@/types";
import { WINGMAN, linksOut } from "./platforms";

/** The two systems as day1 lists them for an admin. */
const APART: Platform[] = [
  { id: "segments", name: "Segments Manager", url: "https://segments-manager.example" },
  { id: "server-scan", name: "Server Scan", url: "https://server-scan.example" },
];

describe("the links out to the systems apart from Wingman", () => {
  it("link each system's own UI under day1's name for it, in day1's order", () => {
    expect(linksOut(APART)).toEqual([
      { id: "segments", label: "Segments Manager", href: "https://segments-manager.example" },
      { id: "server-scan", label: "Server Scan", href: "https://server-scan.example" },
    ]);
    // day1's name is the only source: the web keeps no word of its own
    expect(linksOut([{ ...APART[0], name: "Segments" }])[0].label).toBe("Segments");
  });

  it("list nothing for a system day1 has no address for, and nothing for a viewer", () => {
    expect(linksOut([APART[1]]).map((e) => e.id)).toEqual(["server-scan"]);
    expect(linksOut([{ ...APART[0], url: "" }])).toEqual([]);
    // A viewer: usePlatforms() is [] (day1's read is for admins)
    expect(linksOut([])).toEqual([]);
  });

  it("credits Wingman to the people who built it, each with their years", () => {
    expect(WINGMAN.credits).toEqual([
      { name: "Liad Yahav", years: "2024 – 2026" },
      { name: "Roi Blum", years: "2024 – 2028" },
    ]);
  });
});
