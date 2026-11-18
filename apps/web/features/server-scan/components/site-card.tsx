// What it follows upstream, and at which version: docs/integrations/server-scan.yaml.

import Link from "next/link";
import { SegmentedBar } from "@/components/overview/bars";
import { Skeleton } from "@/components/ui/skeleton";
import { serversHref } from "@/features/server-scan/lib/servers-view";
import {
  HEALTHY_GLYPH,
  cardCounts,
  cardVerdict,
  countBars,
  healthSegments,
  healthSummary,
  installedAvailable,
  type CountBar,
  type HealthSegment,
  type CountKind,
  type SiteCard,
} from "@/features/server-scan/lib/sites";
import { cn } from "@/lib/utils";

/**
 * Wingman's colour for each count: the glyph's shape and the word tell them
 * apart first (server-scan's rule), so MAJOR shares CRITICAL's tone, as on
 * the cluster page's health badge.
 */
/** A count's link: above the card's stretched link, underlined on hover. */
const COUNT_LINK = "relative z-10 rounded-sm underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/50";

const TONE: Record<CountKind, string> = {
  critical: "text-status-error-fg",
  major: "text-status-error-fg",
  warning: "text-status-warning-fg",
  maintenance: "text-status-provisioning-fg",
  unknown: "text-muted-foreground",
};

/** Each health tier's fill, in Wingman's status colours (MAJOR a paler error, as on the Overview's bar). */
const SEGMENT_FILL: Record<HealthSegment["key"], string> = {
  CRITICAL: "bg-status-error",
  MAJOR: "bg-status-error/60",
  WARNING: "bg-status-warning",
  UNKNOWN: "bg-muted-foreground/30",
  MAINTENANCE: "bg-status-provisioning",
  HEALTHY: "bg-status-ready",
};

/**
 * server-scan's stacked health bar (v6.2.0): each tier as wide as its share
 * of the card's servers, worst at the left; a tier above zero keeps 3 pixels,
 * so one critical server in 500 still shows. Its words are its name and tooltip.
 */
function HealthBar({ segments }: { segments: HealthSegment[] }) {
  const words = healthSummary(segments);
  return (
    <div role="img" aria-label={`Health: ${words}`} title={words} data-testid="ss-card-health" className="mt-4">
      <SegmentedBar parts={segments.map((s) => ({ key: s.key, count: s.count, fill: SEGMENT_FILL[s.key] }))} />
    </div>
  );
}

/** A bar's row: above zero a link to its servers (above the card's stretched link), at zero plain. */
const BAR_ROW = "flex items-center gap-2.5 text-xs";

/** One bar as wide as its share of this card's total, in a neutral grey (it is not an alarm). */
function CountBarRow({ bar }: { bar: CountBar }) {
  const body = (
    <>
      <span className="w-16 shrink-0 text-muted-foreground group-hover/bar:text-foreground group-hover/bar:underline">{bar.label}</span>
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        <span className="block h-full rounded-full bg-muted-foreground/45" style={{ width: `${bar.percent}%` }} />
      </span>
      <span className="w-9 shrink-0 text-right tabular-nums text-muted-foreground">{bar.count}</span>
    </>
  );
  const data = { "data-testid": "ss-card-bar", "data-bar": bar.key, "data-group": bar.group };
  if (bar.filter === null) {
    return (
      <div className={BAR_ROW} {...data}>
        {body}
      </div>
    );
  }
  return (
    <Link href={serversHref(bar.filter)} aria-label={`${bar.label}: ${bar.count}`} data-filter={bar.filter} className={cn(COUNT_LINK, "group/bar", BAR_ROW)} {...data}>
      {body}
    </Link>
  );
}

/** Physical and VM, then a bar per vendor (server-scan v6.3.0), each its share of the card's total. */
function CountBars({ bars }: { bars: CountBar[] }) {
  const group = (name: CountBar["group"]) => bars.filter((bar) => bar.group === name).map((bar) => <CountBarRow key={bar.key} bar={bar} />);
  return (
    <div className="mt-4 space-y-3" aria-label="Servers by type and vendor">
      <div className="space-y-1.5">{group("type")}</div>
      <div className="space-y-1.5">{group("vendor")}</div>
    </div>
  );
}

/** The health and maintenance counts above zero, or "all healthy", or "empty". */
function HealthCounts({ card }: { card: SiteCard }) {
  const verdict = cardVerdict(card.stats);
  return (
    <div className="mt-3 flex min-h-4 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {cardCounts(card).map((count) => (
        <Link
          key={count.kind}
          href={serversHref(count.filter)}
          data-testid="ss-card-count"
          data-kind={count.kind}
          data-filter={count.filter}
          className={cn(COUNT_LINK, "inline-flex items-center gap-1.5 font-medium", TONE[count.kind])}
        >
          <span aria-hidden>{count.glyph}</span>
          <span>
            <span className="tabular-nums">{count.count}</span> {count.word}
          </span>
        </Link>
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
 * counts, a site's installed and available servers, its health bar, and the
 * Physical, VM and vendor bars. The card opens the Servers page with its filter
 * (`data-filter`), and each count and bar above zero with its own: the name
 * is the card's link, stretched over it, and the counts and bars are links
 * above it (anchors cannot nest). `emphasis` marks the fleet-wide row.
 */
export function SiteCardView({ card, emphasis = false }: { card: SiteCard; emphasis?: boolean }) {
  const states = installedAvailable(card);
  const bars = countBars(card);
  const segments = healthSegments(card.stats);
  const titleId = `ss-card-${card.key}`;
  return (
    <article
      aria-labelledby={titleId}
      data-testid="ss-card"
      data-card={card.key}
      data-filter={card.filter}
      className={cn(
        "relative rounded-xl border bg-card p-5 transition-colors hover:border-foreground/25 has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-ring/50",
        emphasis && "border-foreground/15 shadow-xs"
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 id={titleId} className="truncate text-sm font-semibold tracking-tight">
          <Link href={serversHref(card.filter)} data-testid="ss-card-link" className="outline-none after:absolute after:inset-0 after:rounded-xl">
            {card.name}
          </Link>
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
            <Link key={s.state} href={serversHref(s.filter)} data-testid="ss-card-state" data-filter={s.filter} className={COUNT_LINK}>
              <span className="font-medium tabular-nums text-foreground">{s.count}</span> {s.word}
            </Link>
          ))}
        </div>
      )}
      {segments.length > 0 && <HealthBar segments={segments} />}
      {bars.length > 0 && <CountBars bars={bars} />}
    </article>
  );
}

/** A card's place while the sites load, about a card's height (its health bar and six bars) so nothing jumps. */
export function SiteCardSkeleton() {
  return (
    <div className="h-[296px] space-y-3 rounded-xl border bg-card p-5" aria-hidden>
      <div className="flex items-baseline justify-between">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-7 w-12" />
      </div>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-3 w-40" />
      <Skeleton className="mt-4 h-2 w-full rounded-full" />
      <div className="space-y-2.5 pt-2">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-1.5 w-full" />
        ))}
      </div>
    </div>
  );
}
