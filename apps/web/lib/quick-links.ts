/**
 * Quick Links (docs/notes/2026-11-12-quick-links-api.md, ADR-0052): the
 * sections and cards day1 generates and reads from the links file, and the
 * status of each link, which day1 checks itself. The browser never pings a
 * link: the status read is day1's cached answer.
 */

import { useQuery } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
import type { ArgoReading, LinkCheck, QuickLinkCard, QuickLinkSection, QuickLinks, QuickLinksStatus } from "@/types";

export const quickLinksKeys = {
  board: ["quick-links"] as const,
  status: ["quick-links", "status"] as const,
};

export const quickLinksApi = {
  board: () => "/api/day1/quick-links",
  status: () => "/api/day1/quick-links/status",
};

/** How often the dots and the ArgoCD counts are read again: day1 keeps each answer for a minute. */
export const STATUS_POLL_MS = 60_000;

/** The sections and cards: fast (the day1 repo's tree, cached, and the links file). */
export function useQuickLinks() {
  return useQuery<QuickLinks>({
    queryKey: quickLinksKeys.board,
    queryFn: () => api.get<QuickLinks>(quickLinksApi.board()),
    staleTime: 30_000,
    // A problem is day1's answer (403 for a viewer): show it, don't ask again
    retry: (count, error) => !isApiError(error) && count < 2,
  });
}

/** Every link's check and every ArgoCD's counts, read once the cards are shown and every minute after. */
export function useQuickLinksStatus(enabled: boolean) {
  return useQuery<QuickLinksStatus>({
    queryKey: quickLinksKeys.status,
    queryFn: () => api.get<QuickLinksStatus>(quickLinksApi.status()),
    enabled,
    staleTime: 30_000,
    refetchInterval: STATUS_POLL_MS,
    retry: (count, error) => !isApiError(error) && count < 2,
  });
}

/** What a search matches in a card: its name, description, link labels and URLs. */
function cardText(card: QuickLinkCard): string {
  return [card.name, card.description ?? "", ...card.links.flatMap((l) => [l.label ?? "", l.url])]
    .join("\n")
    .toLowerCase();
}

/**
 * The sections with only the cards that match `needle` (case-insensitive).
 * A section whose name matches keeps every card; a section left with no
 * card drops out. An empty needle keeps everything.
 */
export function filterSections(sections: QuickLinkSection[], needle: string): QuickLinkSection[] {
  const words = needle.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return sections;
  return sections.flatMap((section) => {
    const name = section.name.toLowerCase();
    const cards = section.cards.filter((card) => {
      const text = `${name}\n${cardText(card)}`;
      return words.every((word) => text.includes(word));
    });
    return cards.length > 0 ? [{ ...section, cards }] : [];
  });
}

/** Every card of every section. */
export const countCards = (sections: QuickLinkSection[]): number =>
  sections.reduce((total, section) => total + section.cards.length, 0);

/** Lookups into one status read: a link's check by its `ping`, an ArgoCD's counts by instance. */
export interface StatusIndex {
  check: (ping: string | null) => LinkCheck | undefined;
  argocd: (instance: string | null) => ArgoReading | undefined;
}

export function indexStatus(status: QuickLinksStatus | undefined): StatusIndex {
  const checks = new Map((status?.checks ?? []).map((c) => [c.url, c]));
  const readings = new Map((status?.argocd ?? []).map((r) => [r.instance, r]));
  return {
    check: (ping) => (ping ? checks.get(ping) : undefined),
    argocd: (instance) => (instance ? readings.get(instance) : undefined),
  };
}

/** "12 s ago", "3 min ago", "2 h ago"; `null` for a missing or unreadable time. */
export function ago(iso: string | null, now: number = Date.now()): string | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.round(minutes / 60)} h ago`;
}

const STATE_WORD = { up: "Up", down: "Down", unknown: "Unknown" } as const;

/**
 * A check in one line, for the dot's tooltip and its accessible name:
 * "Up · answered 200 in 84 ms · checked 12 s ago". Without a check yet:
 * "Not checked yet"; a link with no `ping`: no dot at all.
 */
export function describeCheck(check: LinkCheck | undefined, now?: number): string {
  if (!check) return "Not checked yet";
  const latency = check.latency_ms !== null ? ` in ${check.latency_ms} ms` : "";
  const when = ago(check.checked_at, now);
  return [STATE_WORD[check.state], `${check.reason}${latency}`, when && `checked ${when}`].filter(Boolean).join(" · ");
}
