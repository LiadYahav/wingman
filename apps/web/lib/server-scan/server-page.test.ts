import { describe, expect, it } from "vitest";
import { backHref, nodeServerLink, parseTab, serverHref } from "./server-page";
import { isHealthSeverity } from "./vocabulary";

describe("the server page's address", () => {
  it("puts the tab in the URL, Overview without one", () => {
    expect(serverHref("srv_1")).toBe("/server-scan/servers/srv_1");
    expect(serverHref("srv_1", "history")).toBe("/server-scan/servers/srv_1?tab=history");
    expect(serverHref("a/b c")).toBe("/server-scan/servers/a%2Fb%20c");
  });

  it("reads a tab it knows, else Overview", () => {
    expect(parseTab("network")).toBe("network");
    expect(parseTab("nodes")).toBe("overview");
    expect(parseTab(null)).toBe("overview");
  });

  it("goes back to the Servers view it came from, and never anywhere else", () => {
    expect(backHref("/server-scan/servers?vendor=cisco&page=2")).toBe("/server-scan/servers?vendor=cisco&page=2");
    expect(backHref("/server-scan/servers")).toBe("/server-scan/servers");
    expect(backHref("/inventory")).toBe("/server-scan/servers");
    expect(backHref("/server-scan/servers/srv_1")).toBe("/server-scan/servers");
    expect(backHref("https://elsewhere.example/server-scan/servers")).toBe("/server-scan/servers");
    expect(backHref(null)).toBe("/server-scan/servers");
  });
});

describe("a node's server link", () => {
  const server = { id: "srv_0d48/1", name: "ocp-dell-r660-site1-DL0000123", url: "https://server-scan.example/servers/srv_0d48%2F1" };

  it("is the server's page here, in this tab, for whoever has the Server Scan area", () => {
    expect(nodeServerLink(server, true)).toEqual({
      href: "/server-scan/servers/srv_0d48%2F1",
      inApp: true,
      label: "ocp-dell-r660-site1-DL0000123, its server page",
    });
  });

  it("is server-scan's own page, in a new tab, for anyone else and while that is found out", () => {
    const original = {
      href: server.url,
      inApp: false,
      label: "ocp-dell-r660-site1-DL0000123, its server-scan page (opens in a new tab)",
    };
    expect(nodeServerLink(server, false)).toEqual(original);
    expect(nodeServerLink(server, undefined)).toEqual(original);
  });
});

describe("a component's health word", () => {
  it("is a severity, or a collector's own word (Cisco's UP)", () => {
    expect(isHealthSeverity("CRITICAL")).toBe(true);
    expect(isHealthSeverity("UP")).toBe(false);
  });
});
