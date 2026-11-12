/**
 * Quick Links mocks (docs/notes/2026-11-12-quick-links-api.md), typed so a
 * shape change fails `tsc`. `.example.internal` addresses only: nothing here
 * is a real system.
 */

import type { Page, Route } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, json, mockDashboardApis } from "./api-handlers";
import type { ArgoReading, LinkCheck, QuickLinkCard, QuickLinks, QuickLinkSection, QuickLinksStatus } from "../../types";

const DOMAIN = "example.internal";
export const argocdUrl = (cluster: string) => `https://openshift-gitops-server-openshift-gitops.apps.${cluster}.${DOMAIN}`;
export const consoleUrl = (cluster: string) => `https://console-openshift-console.apps.${cluster}.${DOMAIN}`;

/** A generated card: the cluster's ArgoCD, then its console, each checked. */
export function clusterCard(name: string, overrides: Partial<QuickLinkCard> = {}): QuickLinkCard {
  return {
    id: `cluster:${name}`,
    name,
    description: null,
    icon: "argocd",
    argocd: null,
    links: [
      { label: "ArgoCD", url: argocdUrl(name), ping: argocdUrl(name) },
      { label: "Console", url: consoleUrl(name), ping: consoleUrl(name) },
    ],
    ...overrides,
  };
}

/** A links-file card: one link, checked at `ping` (its URL unless given). */
export function fileCard(section: string, name: string, url: string, overrides: Partial<QuickLinkCard> & { ping?: string | null } = {}): QuickLinkCard {
  const { ping = url, ...rest } = overrides;
  const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return {
    id: `file:${slug(section)}:${slug(name)}`,
    name,
    description: null,
    icon: "link",
    argocd: null,
    links: [{ label: null, url, ping }],
    ...rest,
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
    cards: [clusterCard(HUB, { argocd: HUB })],
  },
  {
    id: "site:site1",
    name: "MCEs in site1",
    description: "Each MCE's ArgoCD and console",
    columns: 4,
    generated: true,
    cards: [
      clusterCard(MCE_A, { description: "OpenShift 4.16.27 · 3 hosted clusters", argocd: MCE_A }),
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
        ping: `https://gitlab.${DOMAIN}`,
      }),
      fileCard("Core GitOps", "ArgoCD Main", `https://argocd.${DOMAIN}`, { icon: "argocd", argocd: "main" }),
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
      fileCard("DC Systems", "Runbooks", `https://wiki.${DOMAIN}/runbooks`, { icon: "no-such-icon", ping: null }),
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

const AT = "2026-11-12T10:00:00Z";

export function check(url: string, overrides: Partial<LinkCheck> = {}): LinkCheck {
  return { url, state: "up", reason: "answered 200", http_status: 200, latency_ms: 84, checked_at: AT, ...overrides };
}

export function argo(instance: string, overrides: Partial<ArgoReading> = {}): ArgoReading {
  return {
    instance,
    counts: {
      applications: 45,
      sync: { synced: 42, out_of_sync: 3, unknown: 0 },
      health: { healthy: 40, progressing: 1, degraded: 2, missing: 1, suspended: 0, unknown: 1 },
    },
    error: null,
    checked_at: AT,
    ...overrides,
  };
}

/** Every ping of `sections` up, but for the overrides by URL; the ArgoCD readings as given. */
export function mockStatus(
  sections: QuickLinkSection[] = SECTIONS,
  { checks = {}, argocd }: { checks?: Record<string, Partial<LinkCheck>>; argocd?: ArgoReading[] } = {}
): QuickLinksStatus {
  const pings = [...new Set(sections.flatMap((s) => s.cards.flatMap((c) => c.links.map((l) => l.ping))))].filter(
    (p): p is string => p !== null
  );
  return {
    checks: pings.map((url) => check(url, checks[url])),
    argocd: argocd ?? [
      argo(HUB),
      argo(MCE_A, { counts: { applications: 12, sync: { synced: 12, out_of_sync: 0, unknown: 0 }, health: { healthy: 12, progressing: 0, degraded: 0, missing: 0, suspended: 0, unknown: 0 } } }),
      argo("main", { counts: null, error: "ArgoCD refused the token (401)" }),
    ],
  };
}

type Handler = (route: Route) => Promise<void> | void;

const answer = (body: object | Handler) => (route: Route) => (typeof body === "function" ? body(route) : json(route, body));

/**
 * Sign in (as a viewer if asked), mock the dashboard's reads and both Quick
 * Links reads. Register a test's own routes after this: mocks match LIFO.
 */
export async function setUpQuickLinks(
  page: Page,
  { board = mockQuickLinks(), status = mockStatus(), viewer = false }: { board?: QuickLinks | Handler; status?: QuickLinksStatus | Handler; viewer?: boolean } = {}
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
  await page.route("**/api/day1/quick-links/status", answer(status));
}

/** day1's answer to a viewer: Quick Links is for admins. */
export const forbidden = (route: Route) => fulfillProblem(route, 403, "FORBIDDEN", "This needs the admin role.");
