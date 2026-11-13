"use client";

import { Server } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { siteCard } from "@/lib/segments/sites";
import { cn } from "@/lib/utils";
import type { SiteSegmentStats } from "@/types/segments";

/**
 * One card per site: allocated out of total, then the allocated count of each
 * type above zero (a plain count: an Available segment has no type). A card
 * filters the table to its site; pressing it again clears that.
 */
export function SiteCards({
  stats,
  site,
  onSite,
}: {
  stats: SiteSegmentStats[];
  site: string | null;
  onSite: (site: string | null) => void;
}) {
  return (
    <section aria-label="Per-site statistics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {stats.map((stat) => {
        const card = siteCard(stat);
        const active = site !== null && site.toLowerCase() === card.site.toLowerCase();
        return (
          <button
            key={card.site}
            type="button"
            data-testid="site-card"
            data-site={card.site}
            aria-pressed={active}
            onClick={() => onSite(active ? null : card.site)}
            className={cn(
              "flex flex-col gap-2.5 rounded-xl border bg-card p-3.5 text-left outline-none transition-colors hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring/50",
              active && "border-primary ring-1 ring-primary/40"
            )}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5 text-sm font-semibold">
                <Server aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{card.site}</span>
              </span>
              <span
                data-testid="site-card-used"
                title={`${card.allocated} of ${card.total} segments allocated`}
                className={cn(
                  "shrink-0 rounded-full px-2 py-px text-xs font-medium tabular-nums",
                  card.full ? "bg-status-warning/15 text-status-warning-fg" : "bg-muted text-muted-foreground"
                )}
              >
                {card.allocated} / {card.total} used
              </span>
            </span>
            {card.types.length === 0 ? (
              <span className="text-xs text-muted-foreground">No allocated segments</span>
            ) : (
              <span className="flex flex-wrap gap-x-3 gap-y-1" aria-label="Allocated segments per type">
                {card.types.map((t) => (
                  <span key={t.type} className="inline-flex items-baseline gap-1 text-xs">
                    <span className="font-mono text-[11px] text-muted-foreground">{t.type}</span>
                    <span className="font-semibold tabular-nums">{t.count}</span>
                  </span>
                ))}
              </span>
            )}
          </button>
        );
      })}
    </section>
  );
}

export function SiteCardsSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-busy="true">
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="space-y-3 rounded-xl border bg-card p-3.5">
          <div className="flex justify-between">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-16 rounded-full" />
          </div>
          <Skeleton className="h-3 w-32" />
        </div>
      ))}
    </div>
  );
}
