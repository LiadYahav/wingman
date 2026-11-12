import { LinkCard } from "./link-card";
import { Skeleton } from "@/components/ui/skeleton";
import type { StatusIndex } from "@/lib/quick-links";
import { cn } from "@/lib/utils";
import type { QuickLinkSection } from "@/types";

/**
 * The grid for a section's `columns` on a wide screen, fewer on narrow ones.
 * Static class names: Tailwind only builds the classes it can read here.
 */
const GRID: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
  5: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5",
  6: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6",
};

export const gridFor = (columns: number): string => GRID[Math.min(6, Math.max(1, Math.round(columns)))] ?? GRID[4];

export function LinkSection({
  section,
  status,
  statusLoading,
}: {
  section: QuickLinkSection;
  status: StatusIndex;
  statusLoading: boolean;
}) {
  const headingId = `quick-links-${section.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  return (
    <section aria-labelledby={headingId} data-testid="quick-link-section" data-section={section.id} data-columns={section.columns}>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h2 id={headingId} className="text-sm font-semibold tracking-tight">
          {section.name}
        </h2>
        <span className="text-xs tabular-nums text-muted-foreground">{section.cards.length}</span>
        {section.description && <p className="w-full text-xs text-muted-foreground sm:w-auto">{section.description}</p>}
      </div>
      <div className={cn("grid gap-3", gridFor(section.columns))}>
        {section.cards.map((card) => (
          <LinkCard key={card.id} card={card} status={status} statusLoading={statusLoading} />
        ))}
      </div>
    </section>
  );
}

/** What the page shows while the sections are on their way. */
export function LinkSectionSkeleton({ cards = 4 }: { cards?: number }) {
  return (
    <div data-testid="quick-links-loading">
      <Skeleton className="mb-3 h-4 w-32" />
      <div className={cn("grid gap-3", gridFor(4))}>
        {Array.from({ length: cards }).map((_, i) => (
          <div key={i} className="flex gap-3 rounded-xl border bg-card p-4">
            <Skeleton className="size-9 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-full" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
