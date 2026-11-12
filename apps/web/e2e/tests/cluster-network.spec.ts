/**
 * The HostedCluster & network card: VLAN and segment from the cluster file,
 * the EPG from segments-manager, and what segments-manager says that
 * disagrees with the file (docs/notes/2026-11-11-cluster-network-api.md, ADR-0039).
 */
import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, json, mockClusterNetwork, mockDashboardApis } from "../fixtures/api-handlers";
import type { ClusterDetail, ClusterNetworkRead, DestinationCharts } from "../../types";

const SITE = "site2";
const MCE = "ocp4-prep-mce-site2-a";
const AMIT = "ocp4-prep-amit-site2-a";

const DETAIL: ClusterDetail = {
  name: AMIT, site: SITE, mce: MCE,
  yaml: 'owner:\n  merkaz: "1"\nmastertag: 4.16.27-x86_64\nvlanId: 412\ndhcp_values:\n  network: "10.20.90.0"\nnodepool: []\n',
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: `sites/${SITE}/mces/${MCE}/hostedClusters/${AMIT}.yaml`,
  last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: null, spec_version: null, created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1", anaf: "2", mador: "3" }, mastertag: "4.16.27-x86_64", platform: "agent", nodepools: [],
    network: { vlan_id: 412, dhcp_network: "10.20.90.0", segment: "10.20.90.0/24" },
    cluster_name: null, automation_keys: ["vlanId", "dhcp_values"],
  },
  hosted_cluster: { cluster_name: "prep-amit-site2-a", name: "ocp4-prep-amit-site2-a", namespace: "hcp-prep-amit-site2-a" },
  naming: { follows_convention: true, env: "prep", short_name: "amit", sequence: "a", problems: [] },
  mce_default_mastertag: "4.16.27-x86_64",
  problems: [],
  segments_manager: null,
};

const CHARTS: DestinationCharts = {
  cluster: AMIT, mce: MCE, id: `hosted:${SITE}:prep:${MCE}:${AMIT}`, kind: "hosted", site: SITE, env: "prep",
  ocp_version: "4.16.27", installed: [], excluded: [], warnings: [], argocd_note: "",
};

const AGREES: ClusterNetworkRead = {
  vlan_id: 412, segment: "10.20.90.0/24", epg: "EPG_site2_HC_412",
  ledger: { vlan_id: 412, cluster_name: AMIT, status: "Allocated", type: "HC", site: SITE },
  problems: [], ledger_error: null,
};

async function openCluster(page: Page, network: ClusterNetworkRead) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(`**/api/day1/clusters/${AMIT}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${AMIT}/drift?**`, (r) =>
    json(r, {
      cluster: AMIT, site: SITE, mce: MCE, state: "not_linked", is_drifted: false, spec_name: null, spec_version: null,
      current_spec_version: null, value_drift: [], addon_drift: [], version_differences: [], error: null,
    })
  );
  await page.route(`**/api/day2/clusters/${AMIT}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${AMIT}/addons?**`, (r) => json(r, CHARTS));
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await mockClusterNetwork(page, AMIT, network);
  await go(page, `/clusters/${AMIT}?site=${SITE}&mce=${MCE}`);
}

test.describe("The HostedCluster & network card", () => {
  test("VLAN and segment from the file, EPG from segments-manager", async ({ page }) => {
    await openCluster(page, AGREES);
    await expect(page.getByTestId("network-vlan")).toHaveText("412");
    await expect(page.getByTestId("network-segment")).toHaveText("10.20.90.0/24");
    await expect(page.getByTestId("network-epg")).toHaveText("EPG_site2_HC_412");
    await expect(page.getByTestId("network-problems")).toHaveCount(0);
  });

  test("what segments-manager says that disagrees with the file is listed under the rows", async ({ page }) => {
    const problem = "segments-manager has VLAN 413 for this segment; the file has 412";
    await openCluster(page, { ...AGREES, ledger: { ...AGREES.ledger!, vlan_id: 413 }, problems: [problem] });
    await expect(page.getByTestId("network-vlan")).toHaveText("412");
    await expect(page.getByTestId("network-problems")).toContainText(problem);
  });

  test("segments-manager failing leaves the file's values and an unknown EPG", async ({ page }) => {
    await openCluster(page, {
      ...AGREES, epg: null, ledger: null,
      ledger_error: "SegmentsManagerUnavailable: segments-manager answered 503 reading segment 10.20.90.0/24",
    });
    await expect(page.getByTestId("network-segment")).toHaveText("10.20.90.0/24");
    await expect(page.getByTestId("network-epg-unknown")).toHaveText("unknown");
    await expect(page.getByTestId("network-epg-unknown")).toHaveAttribute("title", /answered 503/);
  });
});
