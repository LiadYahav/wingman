import { describe, expect, it } from "vitest";
import { serverScanSidebar } from "./sidebar";

const entries = (pathname: string) =>
  serverScanSidebar(pathname).map((s) => [s.label, s.items.map((i) => [i.label, i.href, i.active])]);

describe("the Server Scan sidebar", () => {
  it("lists only the pages Wingman has built, in server-scan's order: Sites, Servers, Confs, Events, Jobs, Rules & Policies, Claude, Architecture", () => {
    expect(entries("/server-scan")).toEqual([
      [
        "Fleet",
        [
          ["Sites", "/server-scan", true],
          ["Servers", "/server-scan/servers", false],
          ["Confs", "/server-scan/confs", false],
        ],
      ],
      ["Activity", [["Events", "/server-scan/events", false], ["Jobs", "/server-scan/jobs", false]]],
      ["Configuration", [["Rules & Policies", "/server-scan/rules", false]]],
      ["Reference", [["Claude", "/server-scan/claude", false], ["Architecture", "/server-scan/architecture", false]]],
    ]);
  });

  it("marks Sites on the area's home only, and Servers or Confs on its page", () => {
    const marked = (pathname: string) => serverScanSidebar(pathname).flatMap((s) => s.items.filter((i) => i.active).map((i) => i.label));
    expect(marked("/server-scan")).toEqual(["Sites"]);
    expect(marked("/server-scan/servers")).toEqual(["Servers"]);
    expect(marked("/server-scan/servers/srv_1")).toEqual(["Servers"]);
    expect(marked("/server-scan/confs")).toEqual(["Confs"]);
  });

  it("marks Events on its page, in an Activity section between Fleet and Configuration", () => {
    const sections = serverScanSidebar("/server-scan/events");
    expect(sections.map((s) => s.label)).toEqual(["Fleet", "Activity", "Configuration", "Reference"]);
    expect(sections.flatMap((s) => s.items.filter((i) => i.active).map((i) => i.key))).toEqual(["events"]);
  });

  it("marks Jobs on its page, in the Activity section after Events", () => {
    const marked = serverScanSidebar("/server-scan/jobs").flatMap((s) => s.items.filter((i) => i.active).map((i) => i.label));
    expect(marked).toEqual(["Jobs"]);
  });

  it("marks Rules & Policies on its page", () => {
    const marked = serverScanSidebar("/server-scan/rules").flatMap((s) => s.items.filter((i) => i.active).map((i) => i.label));
    expect(marked).toEqual(["Rules & Policies"]);
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
