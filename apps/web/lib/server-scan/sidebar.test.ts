import { describe, expect, it } from "vitest";
import { serverScanSidebar } from "./sidebar";

const entries = (pathname: string) =>
  serverScanSidebar(pathname).map((s) => [s.label, s.items.map((i) => [i.label, i.href, i.active])]);

describe("the Server Scan sidebar", () => {
  it("lists only the pages Wingman has built, in server-scan's order: Sites, Servers", () => {
    expect(entries("/server-scan")).toEqual([
      ["Fleet", [["Sites", "/server-scan", true], ["Servers", "/server-scan/servers", false]]],
    ]);
  });

  it("marks Sites on the area's home only, and Servers on its page", () => {
    expect(entries("/server-scan/servers")).toEqual([
      ["Fleet", [["Sites", "/server-scan", false], ["Servers", "/server-scan/servers", true]]],
    ]);
  });

  it("gives every entry a unique key, its test id", () => {
    const keys = serverScanSidebar("/server-scan").flatMap((s) => s.items.map((i) => i.key));
    expect(new Set(keys).size).toBe(keys.length);
  });
});
