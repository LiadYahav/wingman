import { describe, expect, it } from "vitest";
import { clusterOfPath, isSeed, tenantClusters, workspaceOf, WORKSPACES } from "./workspaces";

const admin = { admin: true };

describe("the two workspaces (ADR-0067)", () => {
  it("are Customers, at Wingman's home, then Infrastructure", () => {
    expect(WORKSPACES.map((w) => [w.id, w.label, w.href])).toEqual([
      ["customers", "Customers", "/"],
      ["infrastructure", "Infrastructure", "/infrastructure"],
    ]);
  });

  it("put the MCEs, seeds, inventory and Quick Links in Infrastructure, and the rest in Customers", () => {
    for (const path of ["/infrastructure", "/mces", "/seeds", "/inventory", "/quick-links"]) {
      expect(workspaceOf(path, admin), path).toBe("infrastructure");
    }
    for (const path of ["/", "/clusters", "/clusters/new", "/specs", "/specs/agent", "/addons", "/approvals", "/audit", "/lints"]) {
      expect(workspaceOf(path, { ...admin, previous: "infrastructure" }), path).toBe("customers");
    }
    expect(workspaceOf("/mcesx", admin)).toBe("customers");
  });

  it("put one cluster's pages where its kind belongs, and keep the last workspace until it is known", () => {
    const kv = "/clusters/ocp4-prod-kv-site1-az1-a";
    expect(workspaceOf(kv, { ...admin, kvCluster: true })).toBe("infrastructure");
    expect(workspaceOf(`${kv}/addons`, { ...admin, kvCluster: true })).toBe("infrastructure");
    expect(workspaceOf("/clusters/ocp4-prod-lark-site1", { ...admin, kvCluster: false, previous: "infrastructure" })).toBe("customers");
    expect(workspaceOf(kv, { ...admin, previous: "infrastructure" })).toBe("infrastructure");
    expect(workspaceOf(kv, admin)).toBe("customers");
  });

  it("keep the workspace you came from on Help's pages", () => {
    expect(workspaceOf("/docs", { ...admin, previous: "infrastructure" })).toBe("infrastructure");
    expect(workspaceOf("/settings", { ...admin, previous: "customers" })).toBe("customers");
  });

  it("leave a viewer in Customers, wherever they are", () => {
    for (const path of ["/infrastructure", "/inventory", "/clusters/x", "/docs"]) {
      expect(workspaceOf(path, { admin: false, kvCluster: true, previous: "infrastructure" }), path).toBe("customers");
    }
  });

  it("read one cluster's name from its path, never New Cluster's", () => {
    expect(clusterOfPath("/clusters/ocp4-prod-kv-site1-az1-a/addons")).toBe("ocp4-prod-kv-site1-az1-a");
    expect(clusterOfPath("/clusters/new")).toBeNull();
    expect(clusterOfPath("/clusters")).toBeNull();
    expect(clusterOfPath("/specs/x")).toBeNull();
  });

  it("count a row without a kind as a tenant's, and know a seed by its kind", () => {
    const rows = [{ kind: "tenant" as const }, { kind: "kv" as const }, {}];
    expect(tenantClusters(rows)).toEqual([{ kind: "tenant" }, {}]);
    expect(isSeed({ kind: "seed" })).toBe(true);
    expect(isSeed({})).toBe(false);
  });
});
