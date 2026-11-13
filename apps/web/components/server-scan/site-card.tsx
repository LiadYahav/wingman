import { Skeleton } from "@/components/ui/skeleton";
import {
  HEALTHY_GLYPH,
  cardCounts,
  cardVerdict,
  installedAvailable,
  vendorBars,
  type CountKind,
  type SiteCard,
  type VendorBar,
} from "@/lib/server-scan/sites";
import { cn } from "@/lib/utils";

/**
 * Wingman's colour for each count: the glyph's shape and the word tell them
 * apart first (server-scan's rule), so MAJOR shares CRITICAL's tone, as on
 * the cluster page's health badge.
 */
const TONE: Record<CountKind, string> = {
  critical: "text-status-error-fg",
  major: "text-status-error-fg",
  warning: "text-status-warning-fg",
  maintenance: "text-status-provisioning-fg",
  unknown: "text-muted-foreground",
};

/** Bars as wide as each vendor's share of this card's total, in a neutral grey (they are not alarms). */
function VendorBars({ bars }: { bars: VendorBar[] }) {
  return (
    <div className="mt-4 space-y-1.5" aria-label="Servers per vendor">
      {bars.map((bar) => (
        <div key={bar.vendor} className="flex items-center gap-2.5 text-xs" data-testid="ss-card-vendor">
          <span className="w-16 shrink-0 text-muted-foreground">{bar.label}</span>
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
            <span className="block h-full rounded-full bg-muted-foreground/45" style={{ width: `${bar.percent}%` }} />
          </span>
          <span className="w-9 shrink-0 text-right tabular-nums text-muted-foreground">{bar.count}</span>
        </div>
      ))}
    </div>
  );
}

/** The health and maintenance counts above zero, or "all healthy", or "empty". */
function HealthCounts({ card }: { card: SiteCard }) {
  const verdict = cardVerdict(card.stats);
  return (
    <div className="mt-3 flex min-h-4 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {cardCounts(card).map((count) => (
        <span
          key={count.kind}
          data-testid="ss-card-count"
          data-kind={count.kind}
          data-filter={count.filter}
          className={cn("inline-flex items-center gap-1.5 font-medium", TONE[count.kind])}
        >
          <span aria-hidden>{count.glyph}</span>
          <span>
            <span className="tabular-nums">{count.count}</span> {count.word}
          </span>
        </span>
      ))}
      {verdict === "all-healthy" && (
        <span className="inline-flex items-center gap-1.5 text-status-ready-fg">
          <span aria-hidden>{HEALTHY_GLYPH}</span> all healthy
        </span>
      )}
      {verdict === "empty" && <span className="text-muted-foreground">empty</span>}
    </div>
  );
}

/**
 * One card, as server-scan's Sites page draws it: name and total, then the
 * counts, a site's installed and available servers, and a bar per vendor.
 * Not a link yet: `data-filter` is what Wingman's Servers page will open.
 * `emphasis` marks the fleet-wide row.
 */
export function SiteCardView({ card, emphasis = false }: { card: SiteCard; emphasis?: boolean }) {
  const states = installedAvailable(card);
  const bars = vendorBars(card.stats);
  const titleId = `ss-card-${card.key}`;
  return (
    <article
      aria-labelledby={titleId}
      data-testid="ss-card"
      data-card={card.key}
      data-filter={card.filter}
      className={cn("rounded-xl border bg-card p-5", emphasis && "border-foreground/15 shadow-xs")}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 id={titleId} className="truncate text-sm font-semibold tracking-tight">
          {card.name}
        </h3>
        <span className="text-2xl font-semibold tabular-nums" data-testid="ss-card-total">
          {card.stats.total.toLocaleString()}
        </span>
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">{card.subtitle}</p>
      <HealthCounts card={card} />
      {states.length > 0 && (
        <div className="mt-3 flex items-center gap-x-3 text-xs text-muted-foreground">
          {states.map((s) => (
            <span key={s.state} data-testid="ss-card-state" data-filter={s.filter}>
              <span className="font-medium tabular-nums text-foreground">{s.count}</span> {s.word}
            </span>
          ))}
        </div>
      )}
      {bars.length > 0 && <VendorBars bars={bars} />}
    </article>
  );
}

/** A card's place while the sites load, about a card's height so nothing jumps. */
export function SiteCardSkeleton() {
  return (
    <div className="h-[184px] space-y-3 rounded-xl border bg-card p-5" aria-hidden>
      <div className="flex items-baseline justify-between">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-7 w-12" />
      </div>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-3 w-40" />
      <div className="space-y-2 pt-2">
        <Skeleton className="h-1.5 w-full" />
        <Skeleton className="h-1.5 w-full" />
      </div>
    </div>
  );
}
