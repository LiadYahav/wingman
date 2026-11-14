import { describe, expect, it } from "vitest";
import { serverScanSidebar } from "./sidebar";

const entries = (pathname: string) =>
  serverScanSidebar(pathname).map((s) => [s.label, s.items.map((i) => [i.label, i.href, i.active])]);

describe("the Server Scan sidebar", () => {
  it("lists only the pages Wingman has built, in server-scan's order: Sites, Servers, Claude, Architecture", () => {
    expect(entries("/server-scan")).toEqual([
      ["Fleet", [["Sites", "/server-scan", true], ["Servers", "/server-scan/servers", false]]],
      ["Reference", [["Claude", "/server-scan/claude", false], ["Architecture", "/server-scan/architecture", false]]],
    ]);
  });

  it("marks Sites on the area's home only, and Servers on its page", () => {
    expect(entries("/server-scan/servers")).toEqual([
      ["Fleet", [["Sites", "/server-scan", false], ["Servers", "/server-scan/servers", true]]],
      ["Reference", [["Claude", "/server-scan/claude", false], ["Architecture", "/server-scan/architecture", false]]],
    ]);
  });

  it("marks Claude on its page", () => {
    const claude = serverScanSidebar("/server-scan/claude").flatMap((s) => s.items).filter((i) => i.active);
    expect(claude.map((i) => i.key)).toEqual(["claude"]);
  });

  it("marks Architecture on its page, whichever diagram it shows", () => {
    const active = (pathname: string) =>
      serverScanSidebar(pathname).flatMap((s) => s.items.filter((i) => i.active).map((i) => i.key));
    expect(active("/server-scan/architecture")).toEqual(["architecture"]);
  });

  it("gives every entry a unique key, its test id", () => {
    const keys = serverScanSidebar("/server-scan").flatMap((s) => s.items.map((i) => i.key));
    expect(new Set(keys).size).toBe(keys.length);
  });
});
