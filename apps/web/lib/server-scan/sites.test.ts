/**
 * The Sites cards. The cases and the fixture are server-scan's own
 * (`frontend/src/features/sites/SitesOverviewPage.test.tsx` at 92146d3,
 * decision 18), asked of the pure model instead of the rendered page; a
 * link's `href` there is a card's or count's `filter` here.
 */

import { describe, expect, it } from "vitest";
import type { Breakdown, SiteStats, SiteStatsList } from "@/types/server-scan";
import {
  UNASSIGNED_SITE_ID,
  cardCounts,
  cardVerdict,
  fleetCards,
  installedAvailable,
  siteCards,
  sitesSummary,
  vendorBars,
  vendorLabel,
  withFilter,
} from "./sites";

function breakdown(overrides: Partial<Breakdown> = {}): Breakdown {
  return {
    total: 0,
    by_vendor: [
      { vendor: "dell", count: 0 },
      { vendor: "cisco", count: 0 },
      { vendor: "hp", count: 0 },
      { vendor: "standalone", count: 0 },
    ],
    by_health: { UNKNOWN: 0, HEALTHY: 0, WARNING: 0, MAJOR: 0, CRITICAL: 0 },
    in_maintenance: 0,
    ...overrides,
  };
}

function site(
  site_id: string,
  name: string,
  slices: { UPI: Partial<Breakdown>; HOSTED_CLUSTER: Partial<Breakdown>; AVAILABLE?: Partial<Breakdown> },
): SiteStats {
  const upi = breakdown(slices.UPI);
  const hosted = breakdown(slices.HOSTED_CLUSTER);
  const available = breakdown(slices.AVAILABLE);
  return {
    site_id,
    name,
    ...breakdown({
      total: upi.total + hosted.total,
      by_health: {
        UNKNOWN: 0,
        HEALTHY: 0,
        WARNING: 0,
        MAJOR: (upi.by_health.MAJOR ?? 0) + (hosted.by_health.MAJOR ?? 0),
        CRITICAL: (upi.by_health.CRITICAL ?? 0) + (hosted.by_health.CRITICAL ?? 0),
      },
    }),
    by_installation_type: { UPI: upi, HOSTED_CLUSTER: hosted, MCE: breakdown(), UNCLASSIFIED: breakdown() },
    by_openshift_state: {
      AVAILABLE: available,
      INSTALLED: breakdown({ total: upi.total + hosted.total - available.total }),
      INSTALLED_TO_INVENTORY: breakdown(),
    },
  };
}

/** Fixture-only mirror of server-scan's aggregation, so the answer is consistent; the model reads `fleet` as given. */
function sum(records: Breakdown[]): Breakdown {
  const result = breakdown();
  for (const record of records) {
    result.total += record.total;
    result.in_maintenance += record.in_maintenance;
    for (const entry of record.by_vendor) {
      const existing = result.by_vendor.find((v) => v.vendor === entry.vendor);
      if (existing) existing.count += entry.count;
    }
    for (const [severity, count] of Object.entries(record.by_health)) {
      const key = severity as keyof Breakdown["by_health"];
      result.by_health[key] = (result.by_health[key] ?? 0) + (count ?? 0);
    }
  }
  return result;
}

const SITE_ITEMS = [
  site("tlv", "Tel Aviv", {
    UPI: { total: 30, by_health: { UNKNOWN: 0, HEALTHY: 28, WARNING: 0, MAJOR: 0, CRITICAL: 2 } },
    HOSTED_CLUSTER: { total: 12 },
    AVAILABLE: { total: 7 },
  }),
  site("nyc", "New York City", {
    UPI: { total: 5 },
    HOSTED_CLUSTER: { total: 3, by_health: { UNKNOWN: 0, HEALTHY: 2, WARNING: 0, MAJOR: 0, CRITICAL: 1 } },
    AVAILABLE: { total: 2 },
  }),
];

const slice = (pick: (s: SiteStats) => Breakdown | undefined) => sum(SITE_ITEMS.map((s) => pick(s) ?? breakdown()));

const RESPONSE: SiteStatsList = {
  items: SITE_ITEMS,
  fleet: {
    ...sum(SITE_ITEMS),
    by_installation_type: {
      UPI: slice((s) => s.by_installation_type.UPI),
      HOSTED_CLUSTER: slice((s) => s.by_installation_type.HOSTED_CLUSTER),
      MCE: slice((s) => s.by_installation_type.MCE),
      UNCLASSIFIED: slice((s) => s.by_installation_type.UNCLASSIFIED),
    },
    by_openshift_state: {
      AVAILABLE: slice((s) => s.by_openshift_state.AVAILABLE),
      INSTALLED: slice((s) => s.by_openshift_state.INSTALLED),
      INSTALLED_TO_INVENTORY: slice((s) => s.by_openshift_state.INSTALLED_TO_INVENTORY),
    },
  },
};

const byName = (cards: ReturnType<typeof fleetCards>) => Object.fromEntries(cards.map((c) => [c.name, c]));

describe("the fleet-wide cards", () => {
  it("are read from server-scan's own fleet summary", () => {
    const cards = byName(fleetCards(RESPONSE.fleet));
    expect(cards["Across all sites"].stats.total).toBe(50);
    expect(cards["UPI"].stats.total).toBe(35);
    expect(cards["Hosted cluster"].stats.total).toBe(15);
    // The fixture has no MCE servers; the card is still there, at 0
    expect(cards["MCE"].stats.total).toBe(0);
  });

  it("open the matching pre-filtered server list", () => {
    expect(fleetCards(RESPONSE.fleet).map((c) => [c.name, c.filter])).toEqual([
      ["Across all sites", ""],
      ["UPI", "installation_type=UPI"],
      ["Hosted cluster", "installation_type=HOSTED_CLUSTER"],
      ["MCE", "installation_type=MCE"],
      ["Available", "openshift_state=AVAILABLE"],
      ["Installed", "openshift_state=INSTALLED"],
    ]);
  });

  it("say what each counts", () => {
    expect(fleetCards(RESPONSE.fleet).map((c) => c.subtitle)).toEqual([
      "servers, every site",
      "servers, every site",
      "servers, every site",
      "servers, every site",
      "no cluster holds these",
      "in use by a cluster",
    ]);
  });

  it("count the OpenShift cards off server-scan's own slice", () => {
    // 7 in Tel Aviv + 2 in New York
    expect(byName(fleetCards(RESPONSE.fleet))["Available"].stats.total).toBe(9);
  });

  it("trust server-scan's fleet rather than summing the sites", () => {
    const fleet = { ...breakdown({ total: 999 }), by_installation_type: {}, by_openshift_state: {} };
    const cards = byName(fleetCards(fleet));
    expect(cards["Across all sites"].stats.total).toBe(999);
    expect(cards["UPI"].stats.total).toBe(0);
    expect(cards["Installed"].stats.total).toBe(0);
  });

  it("carry health into the installation-type cards", () => {
    const cards = byName(fleetCards(RESPONSE.fleet));
    expect(cardCounts(cards["UPI"]).map((c) => [c.count, c.word])).toEqual([[2, "critical"]]);
    expect(cardCounts(cards["Hosted cluster"]).map((c) => [c.count, c.word])).toEqual([[1, "critical"]]);
    expect(cardCounts(cards["UPI"])[0].filter).toBe("installation_type=UPI&health_overall=CRITICAL");
  });

  it("have no installed and available counts of their own", () => {
    expect(installedAvailable(fleetCards(RESPONSE.fleet)[0])).toEqual([]);
  });
});

describe("the site cards", () => {
  it("are one per site, opening that site's servers", () => {
    expect(siteCards(RESPONSE.items).map((c) => [c.name, c.subtitle, c.filter])).toEqual([
      ["Tel Aviv", "servers", "site_id=tlv"],
      ["New York City", "servers", "site_id=nyc"],
    ]);
  });

  it("leave Unassigned out while no server landed in it", () => {
    const empty = site(UNASSIGNED_SITE_ID, "Unassigned", { UPI: {}, HOSTED_CLUSTER: {} });
    expect(siteCards([...SITE_ITEMS, empty]).map((c) => c.name)).toEqual(["Tel Aviv", "New York City"]);
  });

  it("show Unassigned as soon as a hostname carries no site", () => {
    const four = site(UNASSIGNED_SITE_ID, "Unassigned", { UPI: { total: 4 }, HOSTED_CLUSTER: {} });
    const card = siteCards([...SITE_ITEMS, four]).at(-1)!;
    expect([card.name, card.subtitle, card.filter]).toEqual(["Unassigned", "no site in hostname", "site_id=unassigned"]);
  });

  it("keep a configured site with no server, at 0", () => {
    const empty = site("five", "Site Five", { UPI: {}, HOSTED_CLUSTER: {} });
    const card = siteCards([empty])[0];
    expect([card.name, card.stats.total, cardVerdict(card.stats)]).toEqual(["Site Five", 0, "empty"]);
  });

  it("count installed and available from the site's own slice, each opening its filter", () => {
    const [tlv, nyc] = siteCards(RESPONSE.items);
    // Tel Aviv: 42 in all, 7 available, so 35 installed
    expect(installedAvailable(tlv).map((s) => [s.count, s.word, s.filter])).toEqual([
      [35, "installed", "site_id=tlv&openshift_state=INSTALLED"],
      [7, "available", "site_id=tlv&openshift_state=AVAILABLE"],
    ]);
    // New York: 8 in all, 2 available, so 6 installed
    expect(installedAvailable(nyc).map((s) => s.count)).toEqual([6, 2]);
  });

  it("turn the maintenance count into the maintenance filter", () => {
    const [tlv] = siteCards([{ ...SITE_ITEMS[0], in_maintenance: 3 }]);
    const maintenance = cardCounts(tlv).find((c) => c.kind === "maintenance")!;
    expect([maintenance.count, maintenance.word, maintenance.glyph]).toEqual([3, "in maintenance", "⏸"]);
    expect(maintenance.filter).toBe("site_id=tlv&maintenance=true");
  });

  it("turn the unknown count into the unknown-health filter", () => {
    const tlv = SITE_ITEMS[0];
    const [card] = siteCards([{ ...tlv, by_health: { ...tlv.by_health, UNKNOWN: 4 } }]);
    const unknown = cardCounts(card).find((c) => c.kind === "unknown")!;
    expect([unknown.count, unknown.glyph, unknown.filter]).toEqual([4, "○", "site_id=tlv&health_overall=UNKNOWN"]);
  });
});

describe("a card's counts", () => {
  const card = (stats: Partial<Breakdown>) => siteCards([{ ...SITE_ITEMS[0], ...breakdown(stats) }])[0];

  it("are only those above zero, in server-scan's order, each with its glyph", () => {
    const counts = cardCounts(
      card({ total: 20, in_maintenance: 1, by_health: { UNKNOWN: 2, HEALTHY: 10, WARNING: 3, MAJOR: 4, CRITICAL: 1 } }),
    );
    expect(counts.map((c) => `${c.glyph} ${c.count} ${c.word}`)).toEqual([
      "◆ 1 critical",
      "⬟ 4 major",
      "▲ 3 warning",
      "⏸ 1 in maintenance",
      "○ 2 unknown",
    ]);
  });

  it("say all healthy only when every server was found healthy, not when none was evaluated", () => {
    expect(cardVerdict(breakdown({ total: 3, by_health: { HEALTHY: 3 } }))).toBe("all-healthy");
    expect(cardVerdict(breakdown({ total: 3, by_health: { UNKNOWN: 3 } }))).toBeNull();
    expect(cardVerdict(breakdown({ total: 3, by_health: { HEALTHY: 2, WARNING: 1 } }))).toBeNull();
    expect(cardVerdict(breakdown())).toBe("empty");
  });

  it("read a severity server-scan left out as zero", () => {
    expect(cardCounts(card({ total: 1, by_health: { HEALTHY: 1 } }))).toEqual([]);
  });
});

describe("the vendor bars", () => {
  it("are each vendor's share of the card's own total, zeroes included", () => {
    const stats = breakdown({
      total: 40,
      by_vendor: [
        { vendor: "dell", count: 30 },
        { vendor: "cisco", count: 10 },
        { vendor: "hp", count: 0 },
      ],
    });
    expect(vendorBars(stats).map((b) => [b.label, b.count, b.percent])).toEqual([
      ["Dell", 30, 75],
      ["Cisco", 10, 25],
      ["HPE", 0, 0],
    ]);
  });

  it("are none for an empty card", () => {
    expect(vendorBars(breakdown())).toEqual([]);
  });

  it("name a vendor server-scan adds later by its own name", () => {
    expect(vendorLabel("kubevirt")).toBe("KubeVirt");
    expect(vendorLabel("standalone")).toBe("Standalone");
    expect(vendorLabel("lenovo")).toBe("lenovo");
  });
});

describe("the header", () => {
  it("counts the fleet and the configured sites, Unassigned left out", () => {
    const unassigned = site(UNASSIGNED_SITE_ID, "Unassigned", { UPI: { total: 4 }, HOSTED_CLUSTER: {} });
    expect(sitesSummary({ ...RESPONSE, items: [...SITE_ITEMS, unassigned] })).toEqual({ servers: 50, sites: 2 });
  });
});

describe("a filter", () => {
  it("adds one parameter, encoded, to the card's", () => {
    expect(withFilter("", "site_id", "bat-yam")).toBe("site_id=bat-yam");
    expect(withFilter("site_id=tlv", "maintenance", "true")).toBe("site_id=tlv&maintenance=true");
    expect(withFilter("", "site_id", "a&b")).toBe("site_id=a%26b");
  });
});
