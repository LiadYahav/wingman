import { describe, expect, it } from "vitest";
import { backHref, parseTab, serverHref } from "./server-page";
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

describe("a component's health word", () => {
  it("is a severity, or a collector's own word (Cisco's UP)", () => {
    expect(isHealthSeverity("CRITICAL")).toBe(true);
    expect(isHealthSeverity("UP")).toBe(false);
  });
});
