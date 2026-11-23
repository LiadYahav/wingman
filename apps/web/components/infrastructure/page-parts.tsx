import { MapPin, TriangleAlert } from "lucide-react";
import { Hint } from "@/components/common/hint";

/** An Infrastructure page's title and what it holds. */
export function PageHeader({ title, subtitle, children }: { title: string; subtitle: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
          {title}
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5 max-w-2xl text-pretty">{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

/** A site's heading above its folders. */
export function SiteHeading({ site, count }: { site: string; count: string }) {
  return (
    <h2 className="flex items-baseline gap-2 text-sm font-semibold">
      <MapPin aria-hidden className="h-3.5 w-3.5 shrink-0 self-center text-muted-foreground" />
      <span className="break-all">{site}</span>
      <span className="text-xs font-normal text-muted-foreground">{count}</span>
    </h2>
  );
}

/** A name that does not follow its kind's pattern: a quiet mark, its problems in a tooltip. */
export function OffConvention({ problems, testId }: { problems: string[]; testId?: string }) {
  if (problems.length === 0) return null;
  return (
    <Hint hint={problems.join(" ")} label="Off-convention name" testId={testId}>
      <span className="inline-flex items-center gap-1 rounded-full bg-status-warning/12 px-2 py-0.5 text-[11px] font-medium text-status-warning-fg">
        <TriangleAlert aria-hidden className="h-3 w-3" />
        Off-convention
      </span>
    </Hint>
  );
}

/** A small chip: an availability zone, an environment. */
export function Chip({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <span title={title} className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
      {children}
    </span>
  );
}
