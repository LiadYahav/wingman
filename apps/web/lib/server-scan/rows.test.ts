/**
 * The Servers page's pure functions. The cases are server-scan's own
 * (`frontend/src/features/inventory/rows.test.ts` at 92146d3, decision 18),
 * ported as they are: the same fleet, the same expectations.
 */

import { describe, expect, it } from "vitest";
import type { ServerRow } from "@/types/server-scan-servers";
import {
  dropdownFacetCounts,
  filterRows,
  parseSearch,
  searchRows,
} from "./rows";

function row(overrides: Partial<ServerRow> = {}): ServerRow {
  return {
    id: overrides.name ?? "srv_1",
    name: "srv-1",
    vendor: "dell",
    model: "R760",
    site_id: "tlv",
    source_provider: "OPENMANAGE",
    installation_type: "UPI",
    health: "HEALTHY",
    maintenance: { enabled: false, reason: null },
    reservation: {
      held: false,
      holder: null,
      mce_cluster: null,
      infra_env: null,
      expires_at: null,
    },
    openshift_state: "AVAILABLE",
    cluster_name: null,
    mce_name: null,
    openshift_reported_name: null,
    contested_with: null,
    profile_template_name: null,
    last_seen_at: null,
    stale: false,
    reachable: true,
    serial: "SN1",
    bmc_host: "bmc-1.example",
    macs: ["aa:bb:cc:dd:ee:01"],
    ...overrides,
  };
}

const FLEET = [
  row({ name: "srv-10", cluster_name: "b" }),
  row({
    name: "srv-2",
    vendor: "cisco",
    site_id: null,
    cluster_name: "a",
    stale: true,
  }),
  row({
    name: "srv-1",
    maintenance: { enabled: true, reason: "psu" },
    health: "CRITICAL",
  }),
];

describe("filterRows", () => {
  it("matches every set filter and treats blanks as any", () => {
    expect(filterRows(FLEET, { vendor: ["cisco"] }).map((r) => r.name)).toEqual(
      ["srv-2"],
    );
    expect(
      filterRows(FLEET, { vendor: [], maintenance: "only" }).map((r) => r.name),
    ).toEqual(["srv-1"]);
    expect(
      filterRows(FLEET, { maintenance: "exclude" }).map((r) => r.name),
    ).toEqual(["srv-10", "srv-2"]);
    expect(
      filterRows(FLEET, { stale: true, health: ["HEALTHY"] }),
    ).toHaveLength(1);
    expect(filterRows(FLEET, {})).toHaveLength(3);
  });

  describe("several values per dropdown", () => {
    const fleet = [
      row({ name: "dell-a", vendor: "dell", openshift_state: "AVAILABLE" }),
      row({ name: "dell-i", vendor: "dell", openshift_state: "INSTALLED" }),
      row({ name: "hp-a", vendor: "hp", openshift_state: "AVAILABLE" }),
      row({ name: "cisco-a", vendor: "cisco", openshift_state: "AVAILABLE" }),
    ];
    const names = (f: Parameters<typeof filterRows>[1]) =>
      filterRows(fleet, f).map((r) => r.name);

    it("ORs the values of one dropdown", () => {
      expect(names({ vendor: ["dell", "hp"] })).toEqual([
        "dell-a",
        "dell-i",
        "hp-a",
      ]);
    });

    it("ANDs across dropdowns: all Dell and HP that are available", () => {
      expect(
        names({ vendor: ["dell", "hp"], openshift_state: ["AVAILABLE"] }),
      ).toEqual(["dell-a", "hp-a"]);
    });

    it("treats an empty list as all", () => {
      expect(names({ vendor: [], source_provider: [] })).toHaveLength(4);
    });

    it("matches a row with no source against a source filter only if listed", () => {
      const rows = [row({ name: "x", source_provider: null })];
      expect(filterRows(rows, { source_provider: ["OPENMANAGE"] })).toEqual([]);
    });

    it("counts each option over the rows the OTHER filters leave", () => {
      const counts = dropdownFacetCounts(fleet, {
        vendor: ["dell"],
        openshift_state: ["AVAILABLE"],
      });
      // Vendor counts ignore the vendor filter itself: ticking HP would add 1.
      expect(counts.vendor).toEqual({ dell: 1, hp: 1, cisco: 1 });
      // Installation counts ignore the installation filter: Dell has one of each.
      expect(counts.openshift_state).toEqual({ AVAILABLE: 1, INSTALLED: 1 });
      // The total is the fully filtered set.
      expect(counts.total).toBe(1);
    });
  });

  it("keeps the maintenance counts whole, and lets the other counts follow the mode", () => {
    const fleet = [
      row({ name: "a", health: "HEALTHY" }),
      row({ name: "b", health: "HEALTHY", maintenance: { enabled: true, reason: "psu" } }),
      row({ name: "c", health: "CRITICAL", maintenance: { enabled: true, reason: "disk" } }),
    ];
    const counts = dropdownFacetCounts(fleet, { health: ["HEALTHY"], maintenance: "exclude" });
    // The Include/Hide/Only control still shows every number it could switch to.
    expect(counts.maintenance).toEqual({ false: 1, true: 1 });
    // Health options follow the mode: with maintenance hidden, CRITICAL has nothing to add.
    expect(counts.health).toEqual({ HEALTHY: 1 });
    expect(counts.total).toBe(1);
  });

  it("maps the unassigned site to a null site_id", () => {
    expect(
      filterRows(FLEET, { site_id: ["unassigned"] }).map((r) => r.name),
    ).toEqual(["srv-2"]);
    expect(filterRows(FLEET, { site_id: ["tlv"] })).toHaveLength(2);
  });

  it("keeps every row sharing a name with another row, and only those", () => {
    const fleet = [
      row({ name: "ocp4-five-compute-06", vendor: "hp" }),
      row({ name: "ocp4-five-compute-06", vendor: "cisco" }),
      row({ name: "ocp4-five-compute-07" }),
    ];
    expect(filterRows(fleet, { duplicate: true }).map((r) => r.vendor)).toEqual(
      ["hp", "cisco"],
    );
  });

  it("still finds a duplicate pair split by another active filter", () => {
    // Filtering by vendor alone would hide one side of the pair; the
    // duplicate count must still be computed over the whole fleet.
    const fleet = [
      row({ name: "ocp4-five-compute-06", vendor: "hp" }),
      row({ name: "ocp4-five-compute-06", vendor: "cisco" }),
    ];
    expect(
      filterRows(fleet, { duplicate: true, vendor: ["hp"] }).map((r) => r.name),
    ).toEqual(["ocp4-five-compute-06"]);
  });

  it("keeps only rows whose membership is contested", () => {
    const fleet = [
      row({ name: "a", contested_with: "mce-b" }),
      row({ name: "b" }),
    ];
    expect(filterRows(fleet, { contested: true }).map((r) => r.name)).toEqual([
      "a",
    ]);
  });

  it("finds nothing when no name repeats", () => {
    expect(filterRows(FLEET, { duplicate: true })).toHaveLength(0);
  });

  it("keeps only rows OpenShift reports under a different name (ADR-0036)", () => {
    const fleet = [
      row({
        name: "ocp-toto-compute-01",
        openshift_reported_name: "ocp-tomer-compute-01",
      }),
      row({ name: "ocp-tlv-compute-02", openshift_reported_name: null }),
    ];
    expect(
      filterRows(fleet, { nameMismatch: true }).map((r) => r.name),
    ).toEqual(["ocp-toto-compute-01"]);
  });

  it("keeps only donors: maintenance whose reason says donor, in any case (ADR-0038)", () => {
    const fleet = [
      row({
        name: "donor-a",
        maintenance: { enabled: true, reason: "DONOR - DIMM B3 bad" },
      }),
      row({
        name: "psu-swap",
        maintenance: { enabled: true, reason: "psu swap" },
      }),
      row({
        name: "was-donor",
        maintenance: { enabled: false, reason: "donor" },
      }),
    ];
    expect(filterRows(fleet, { donor: true }).map((r) => r.name)).toEqual([
      "donor-a",
    ]);
  });
});

describe("searchRows", () => {
  it("matches the same fields the API's token search indexes (vendor and site included)", () => {
    expect(searchRows(FLEET, "cisco").map((r) => r.name)).toEqual(["srv-2"]);
    expect(searchRows(FLEET, "tlv")).toHaveLength(2);
    expect(searchRows(FLEET, "upi")).toHaveLength(3);
  });

  it("is a case-insensitive substring over name, model, serial and BMC host", () => {
    expect(searchRows(FLEET, "RV-1").map((r) => r.name)).toEqual([
      "srv-10",
      "srv-1",
    ]);
    expect(searchRows(FLEET, "r76")).toHaveLength(3);
    expect(searchRows(FLEET, "sn1")).toHaveLength(3);
    expect(searchRows(FLEET, "bmc-1.ex")).toHaveLength(3);
    expect(searchRows(FLEET, "   ")).toBe(FLEET);
  });

  describe("explicit syntax", () => {
    const bmcs = [
      "10.0.0.1",
      "10.0.0.10",
      "10.0.0.11",
      "10.0.0.13",
      "10.0.0.17",
    ].map((bmc_host) => row({ name: `srv-${bmc_host}`, bmc_host }));
    const hosts = (query: string) =>
      searchRows(bmcs, query).map((r) => r.bmc_host);

    it("treats plain text as a substring, so 10.0.0.1 also finds .10 to .17", () => {
      expect(hosts("10.0.0.1")).toHaveLength(5);
    });

    it("treats text in quotes as a whole-value match", () => {
      expect(hosts('"10.0.0.1"')).toEqual(["10.0.0.1"]);
      expect(hosts('"10.0.0.1"')).not.toContain("10.0.0.10");
    });

    it("treats text between slashes as a case-insensitive regex", () => {
      expect(hosts(String.raw`/10\.0\.0\.(1|13)$/`)).toEqual([
        "10.0.0.1",
        "10.0.0.13",
      ]);
      expect(hosts(String.raw`/^10\.0\.0\.1[0-3]$/`)).toEqual([
        "10.0.0.10",
        "10.0.0.11",
        "10.0.0.13",
      ]);
      expect(searchRows([row({ name: "OCP-Dell" })], "/^ocp-/")).toHaveLength(
        1,
      );
    });

    it("matches an exact MAC, colon or bare", () => {
      const rows = [row({ macs: ["aa:bb:cc:dd:ee:ff"] })];
      expect(searchRows(rows, '"aa:bb:cc:dd:ee:ff"')).toHaveLength(1);
      expect(searchRows(rows, '"aabbccddeeff"')).toHaveLength(1);
      expect(searchRows(rows, '"aa:bb:cc"')).toHaveLength(0);
    });

    it("reports a bad regex and keeps every row instead of blanking the table", () => {
      expect(parseSearch("/10.0.0.(/").error).toMatch(/invalid regex/i);
      expect(searchRows(bmcs, "/10.0.0.(/")).toHaveLength(5);
      expect(parseSearch(`/${"a".repeat(65)}/`).error).toMatch(
        /longer than 64/,
      );
      expect(parseSearch("/10\\.0/").error).toBeNull();
    });
  });

  it("matches a MAC in colon or bare-hex form", () => {
    const rows = [
      row({ macs: ["aa:bb:cc:dd:ee:ff"] }),
      row({ name: "other", macs: [] }),
    ];
    expect(searchRows(rows, "bb:cc:dd")).toHaveLength(1);
    expect(searchRows(rows, "BBCCDD")).toHaveLength(1);
    expect(searchRows(rows, "aa-bb-cc")).toHaveLength(1);
    expect(searchRows(rows, "zz")).toHaveLength(0);
  });
});
