import { describe, expect, it } from "vitest";
import { areaById, areaOf, areasFor, chromeArea } from "./areas";

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
    expect(areasFor({ segments: true }).map((a) => [a.label, a.href])).toEqual([
      ["Wingman", "/"],
      ["Segments", "/segments"],
    ]);
    expect(areasFor({ segments: false }).map((a) => a.id)).toEqual(["wingman"]);
  });

  it("lists Server Scan after Segments, only for someone who has it", () => {
    expect(areasFor({ segments: true, "server-scan": true }).map((a) => [a.label, a.href])).toEqual([
      ["Wingman", "/"],
      ["Segments", "/segments"],
      ["Server Scan", "/server-scan"],
    ]);
    expect(areasFor({ segments: false, "server-scan": true }).map((a) => a.id)).toEqual(["wingman", "server-scan"]);
    // Still being found out: not listed yet
    expect(areasFor({ "server-scan": undefined }).map((a) => a.id)).toEqual(["wingman"]);
  });

  it("gives each area its brand: Wingman's logo, segments-manager's rack and name", () => {
    expect(areaById("wingman").brand).toEqual({ name: "Wingman", mark: "wingman-logo" });
    expect(areaById("segments").brand).toEqual({ name: "Segments Manager", mark: "server" });
    expect(areaById("segments").href).toBe("/segments");
    expect(areaById("server-scan").brand).toEqual({ name: "Server Scan", mark: "server-scan-icon" });
    expect(areaById("server-scan").href).toBe("/server-scan");
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
