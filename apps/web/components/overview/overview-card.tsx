import Link from "next/link";
import { useId, type ReactNode } from "react";
import { ArrowRight, Info } from "lucide-react";
import { Hint } from "@/components/common/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * One of the Overview's cards: a title (with what its numbers count, in a
 * tooltip), a link to the page that shows the rest, and its body.
 */
export function OverviewCard({
  title,
  hint,
  href,
  linkLabel = "View all",
  className,
  children,
  ...props
}: {
  title: string;
  /** What the card's numbers count. */
  hint?: ReactNode;
  href: string;
  linkLabel?: string;
  className?: string;
  children: ReactNode;
  "data-testid"?: string;
}) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className={cn("bg-card rounded-xl border shadow-sm p-5", className)} {...props}>
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex min-w-0 items-center gap-1">
          <h2 id={titleId} className="text-sm font-semibold">{title}</h2>
          {hint && (
            <Hint hint={hint} label={`About ${title}`}>
              <Info aria-hidden className="h-3.5 w-3.5 text-muted-foreground" />
            </Hint>
          )}
        </div>
        <Link href={href} className="text-xs text-primary hover:underline flex shrink-0 items-center gap-1">
          {linkLabel} <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
      {children}
    </section>
  );
}

/** A card's rows while they load. */
export function RowsSkeleton({ rows = 3, className = "h-11" }: { rows?: number; className?: string }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className={cn("w-full rounded-lg", className)} />)}
    </div>
  );
}
