/**
 * Quick Links mocks (docs/notes/2026-11-12-quick-links-api.md), typed so a
 * shape change fails `tsc`. `.example.internal` addresses only: nothing here
 * is a real system.
 */

import type { Page, Route } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, json, mockDashboardApis } from "./api-handlers";
import type { QuickLinkCard, QuickLinks, QuickLinkSection } from "../../types";

const DOMAIN = "example.internal";
export const argocdUrl = (cluster: string) => `https://openshift-gitops-server-openshift-gitops.apps.${cluster}.${DOMAIN}`;
export const consoleUrl = (cluster: string) => `https://console-openshift-console.apps.${cluster}.${DOMAIN}`;

/** A generated card: the cluster's ArgoCD, then its console. */
export function clusterCard(name: string, overrides: Partial<QuickLinkCard> = {}): QuickLinkCard {
  return {
    id: `cluster:${name}`,
    name,
    description: null,
    icon: "argocd",
    links: [
      { label: "ArgoCD", url: argocdUrl(name) },
      { label: "Console", url: consoleUrl(name) },
    ],
    ...overrides,
  };
}

/** A links-file card: one link. */
export function fileCard(section: string, name: string, url: string, overrides: Partial<QuickLinkCard> = {}): QuickLinkCard {
  const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return {
    id: `file:${slug(section)}:${slug(name)}`,
    name,
    description: null,
    icon: "link",
    links: [{ label: null, url }],
    ...overrides,
  };
}

export const HUB = "hub-prod";
export const MCE_A = "ocp4-prod-mce-site1-a";
export const MCE_B = "ocp4-prep-mce-site1-a";
export const MCE_C = "ocp4-prod-mce-site2-a";

export const SECTIONS: QuickLinkSection[] = [
  {
    id: "hub",
    name: "Hub",
    description: "The cluster Wingman runs on",
    columns: 4,
    generated: true,
    cards: [clusterCard(HUB)],
  },
  {
    id: "site:site1",
    name: "MCEs in site1",
    description: "Each MCE's ArgoCD and console",
    columns: 4,
    generated: true,
    cards: [
      clusterCard(MCE_A, { description: "OpenShift 4.16.27 · 3 hosted clusters" }),
      clusterCard(MCE_B, { description: "OpenShift 4.17.12 · 1 hosted cluster" }),
    ],
  },
  {
    id: "site:site2",
    name: "MCEs in site2",
    description: "Each MCE's ArgoCD and console",
    columns: 4,
    generated: true,
    cards: [clusterCard(MCE_C, { description: "OpenShift 4.16.27 · 0 hosted clusters" })],
  },
  {
    id: "file:core-gitops",
    name: "Core GitOps",
    description: null,
    columns: 2,
    generated: false,
    cards: [
      fileCard("Core GitOps", "GitLab GitOps Project", `https://gitlab.${DOMAIN}/platform/gitops`, {
        description: "Main GitOps repository",
        icon: "gitlab",
      }),
      fileCard("Core GitOps", "ArgoCD Main", `https://argocd.${DOMAIN}`, { icon: "argocd" }),
    ],
  },
  {
    id: "file:dc-systems",
    name: "DC Systems",
    description: "Hardware managers",
    columns: 3,
    generated: false,
    cards: [
      fileCard("DC Systems", "NetBox", `https://netbox.${DOMAIN}`, { description: "IPAM / DCIM", icon: "network" }),
      fileCard("DC Systems", "OpenManage", `https://openmanage.${DOMAIN}`, { description: "Dell OpenManage", icon: "dell" }),
      fileCard("DC Systems", "Runbooks", `https://wiki.${DOMAIN}/runbooks`, { icon: "no-such-icon" }),
    ],
  },
];

export function mockQuickLinks(overrides: Partial<QuickLinks> = {}): QuickLinks {
  return {
    sections: SECTIONS,
    problems: [],
    links_file: { path: "/etc/wingman/quick-links/links.yaml", state: "loaded", problems: [] },
    ...overrides,
  };
}

type Handler = (route: Route) => Promise<void> | void;

const answer = (body: object | Handler) => (route: Route) => (typeof body === "function" ? body(route) : json(route, body));

/**
 * Sign in (as a viewer if asked), mock the dashboard's reads and the Quick
 * Links read. Register a test's own routes after this: mocks match LIFO.
 */
export async function setUpQuickLinks(
  page: Page,
  { board = mockQuickLinks(), viewer = false }: { board?: QuickLinks | Handler; viewer?: boolean } = {}
) {
  await injectAdminAuth(page);
  if (viewer) {
    await page.addInitScript(() => {
      const state = { state: { user: { username: "vera", groups: ["wingman-viewers"], uid: "vera", full_name: "Vera Viewer", role: "viewer" }, isAuthenticated: true }, version: 0 };
      localStorage.setItem("wingman-auth", JSON.stringify(state));
    });
  }
  await mockDashboardApis(page);
  await page.route("**/api/day1/quick-links", answer(board));
}

/** day1's answer to a viewer: Quick Links is for admins. */
export const forbidden = (route: Route) => fulfillProblem(route, 403, "FORBIDDEN", "This needs the admin role.");
