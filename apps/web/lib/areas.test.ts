import { describe, expect, it } from "vitest";
import type { Platform } from "@/types";
import { areaById, areaOf, chromeArea, switchEntries } from "./areas";

/** The two systems as day1 lists them with both areas off (its default since 2026-11-23). */
const APART: Platform[] = [
  { id: "segments", name: "Segments Manager", url: "https://segments-manager.example", area: false },
  { id: "server-scan", name: "Server Scan", url: "https://server-scan.example", area: false },
];
const entry = (e: { id: string; href: string; external: boolean }) => [e.id, e.href, e.external];

describe("the areas", () => {
  it("puts /segments and below in Segments, everything else in Wingman", () => {
    expect(areaOf("/segments")).toBe("segments");
    expect(areaOf("/segments/site1")).toBe("segments");
    expect(areaOf("/")).toBe("wingman");
    expect(areaOf("/clusters/ocp4-prod-herzi-site1")).toBe("wingman");
    expect(areaOf("/segments-old")).toBe("wingman");
  });

  it("puts /server-scan and below in Server Scan", () => {
    expect(areaOf("/server-scan")).toBe("server-scan");
    expect(areaOf("/server-scan/servers")).toBe("server-scan");
    expect(areaOf("/server-scans")).toBe("wingman");
  });

  it("lists Segments only for someone who has it", () => {
    expect(switchEntries({ segments: true }).map((e) => [e.label, e.href, e.external])).toEqual([
      ["Wingman", "/", false],
      ["Segments", "/segments", false],
    ]);
    expect(switchEntries({ segments: false }).map((e) => e.id)).toEqual(["wingman"]);
  });

  it("lists Server Scan after Segments, only for someone who has it", () => {
    expect(switchEntries({ segments: true, "server-scan": true }).map((e) => [e.label, e.href])).toEqual([
      ["Wingman", "/"],
      ["Segments", "/segments"],
      ["Server Scan", "/server-scan"],
    ]);
    expect(switchEntries({ segments: false, "server-scan": true }).map((e) => e.id)).toEqual(["wingman", "server-scan"]);
    // Still being found out: not listed yet
    expect(switchEntries({ "server-scan": undefined }).map((e) => e.id)).toEqual(["wingman"]);
  });

  it("links each system's own UI, in a new tab, while its area is off", () => {
    const off = { segments: false, "server-scan": false };
    expect(switchEntries(off, APART).map((e) => [e.label, e.href, e.external])).toEqual([
      ["Wingman", "/", false],
      ["Segments", "https://segments-manager.example", true],
      ["Server Scan", "https://server-scan.example", true],
    ]);
    // Known from day1's list before the area's own read answers
    expect(switchEntries({}, APART).map(entry)).toEqual([
      ["wingman", "/", false],
      ["segments", "https://segments-manager.example", true],
      ["server-scan", "https://server-scan.example", true],
    ]);
  });

  it("opens an area that is on here, and links out only to the one that is off", () => {
    const serverScanOn: Platform[] = [APART[0], { ...APART[1], area: true }];
    expect(switchEntries({ segments: false, "server-scan": true }, serverScanOn).map(entry)).toEqual([
      ["wingman", "/", false],
      ["segments", "https://segments-manager.example", true],
      ["server-scan", "/server-scan", false],
    ]);
    // An area day1 says is on, while its own read is still on its way: not listed yet
    expect(switchEntries({}, serverScanOn).map((e) => e.id)).toEqual(["wingman", "segments"]);
  });

  it("lists nothing more for a system day1 has no address for, and a viewer gets no list", () => {
    expect(switchEntries({}, [APART[1]]).map((e) => e.id)).toEqual(["wingman", "server-scan"]);
    expect(switchEntries({}, [{ ...APART[0], url: "" }]).map((e) => e.id)).toEqual(["wingman"]);
    // A viewer: no area, and usePlatforms() is [] (day1's read is for admins)
    expect(switchEntries({ segments: false, "server-scan": false }, []).map((e) => e.id)).toEqual(["wingman"]);
  });

  it("gives each area its brand: Wingman's logo, segments-manager's rack and name", () => {
    expect(areaById("wingman").brand).toEqual({ name: "Wingman", mark: "wingman-logo" });
    expect(areaById("segments").brand).toEqual({ name: "Segments Manager", mark: "server" });
    expect(areaById("segments").href).toBe("/segments");
    expect(areaById("server-scan").brand).toEqual({ name: "Server Scan", mark: "server-scan-icon" });
    expect(areaById("server-scan").href).toBe("/server-scan");
  });

  it("credits each area to the people who built it, each with their years", () => {
    const roi = { name: "Roi Blum", years: "2024 – 2028" };
    expect(areaById("wingman").credits).toEqual([{ name: "Liad Yahav", years: "2024 – 2026" }, roi]);
    expect(areaById("segments").credits).toEqual([roi, { name: "Itay Herzberg", years: "2026 – 2028" }]);
    expect(areaById("server-scan").credits).toEqual([roi, { name: "Tomer Karniol", years: "2025 – 2042" }]);
  });

  it("dresses a page in its area's chrome only for someone who has the area", () => {
    expect(chromeArea("/segments", { segments: true })).toBe("segments");
    expect(chromeArea("/segments", { segments: undefined })).toBe("segments");
    expect(chromeArea("/segments", { segments: false })).toBe("wingman");
    expect(chromeArea("/clusters", { segments: true })).toBe("wingman");
    expect(chromeArea("/server-scan", { "server-scan": true })).toBe("server-scan");
    expect(chromeArea("/server-scan", { "server-scan": undefined })).toBe("server-scan");
    expect(chromeArea("/server-scan", { segments: true, "server-scan": false })).toBe("wingman");
    expect(chromeArea("/segments", { segments: true, "server-scan": false })).toBe("segments");
  });
});
