import { describe, expect, it } from "vitest";
import type { Platform } from "@/types";
import { WINGMAN, switchEntries } from "./areas";

/** The two systems as day1 lists them for an admin. */
const APART: Platform[] = [
  { id: "segments", name: "Segments Manager", url: "https://segments-manager.example" },
  { id: "server-scan", name: "Server Scan", url: "https://server-scan.example" },
];
const entry = (e: { id: string; label: string; href: string; external: boolean }) => [e.id, e.label, e.href, e.external];

describe("the top bar's platforms", () => {
  it("links each system's own UI, in a new tab, after Wingman's home", () => {
    expect(switchEntries(APART).map(entry)).toEqual([
      ["wingman", "Wingman", "/", false],
      ["segments", "Segments", "https://segments-manager.example", true],
      ["server-scan", "Server Scan", "https://server-scan.example", true],
    ]);
  });

  it("lists nothing more for a system day1 has no address for, and a viewer gets no list", () => {
    expect(switchEntries([APART[1]]).map((e) => e.id)).toEqual(["wingman", "server-scan"]);
    expect(switchEntries([{ ...APART[0], url: "" }]).map((e) => e.id)).toEqual(["wingman"]);
    // A viewer: usePlatforms() is [] (day1's read is for admins)
    expect(switchEntries([]).map((e) => e.id)).toEqual(["wingman"]);
  });

  it("credits Wingman to the people who built it, each with their years", () => {
    expect(WINGMAN.credits).toEqual([
      { name: "Liad Yahav", years: "2024 – 2026" },
      { name: "Roi Blum", years: "2024 – 2028" },
    ]);
  });
});
