/**
 * Quick Links (docs/notes/2026-11-12-quick-links-api.md, ADR-0052): the
 * sections and cards day1 generates and reads from the links file. A card is
 * links only: neither Wingman nor the browser checks what they point at.
 */

import { useQuery } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
import type { QuickLinkCard, QuickLinkSection, QuickLinks } from "@/types";

export const quickLinksKeys = {
  board: ["quick-links"] as const,
};

export const quickLinksApi = {
  board: () => "/api/day1/quick-links",
};

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
