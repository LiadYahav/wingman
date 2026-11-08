import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { Inbox, SearchX, type LucideIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * A list with nothing in it: what would be here, and the next step when the
 * viewer can take one. Inside a card, a panel or a table cell it stands bare;
 * `bordered` frames it when it stands alone on the page.
 *
 * Loading is a skeleton and a failed read is a `ProblemList`, never this: an
 * empty state claims the list is known to be empty.
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  tone = "neutral",
  bordered = false,
  className,
  ...props
}: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  /** The next step: an `EmptyStateLink`, a `ClearFilters`, or any button. */
  action?: ReactNode;
  /** `success` when nothing here is good news (no findings, nothing to approve). */
  tone?: "neutral" | "success";
  bordered?: boolean;
} & Omit<ComponentProps<"div">, "title">) {
  return (
    <div
      data-slot="empty-state"
      className={cn(
        "flex flex-col items-center justify-center px-4 py-10 text-center",
        bordered && "rounded-xl border border-dashed bg-card/40 py-14",
        className
      )}
      {...props}
    >
      <div
        className={cn(
          "mb-3 rounded-full p-3",
          tone === "success" ? "bg-status-ready/15 text-status-ready" : "bg-muted text-muted-foreground"
        )}
      >
        <Icon className="h-6 w-6" aria-hidden />
      </div>
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {description && (
        <p className="mt-1 max-w-sm text-xs text-balance text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-4 flex flex-wrap items-center justify-center gap-2">{action}</div>}
    </div>
  );
}

/** The usual next step of an empty state: a page to go to. */
export function EmptyStateLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className={buttonVariants({ variant: "outline", size: "sm" })}>
      {children}
    </Link>
  );
}

/** The empty state of a list its filters or search emptied: say so, and offer to clear them. */
export function NoMatches({
  what,
  onClear,
  clearLabel = "Clear filters",
  ...props
}: {
  /** The list, plural: "clusters", "merge requests". */
  what: string;
  onClear: () => void;
  clearLabel?: string;
  bordered?: boolean;
} & Omit<ComponentProps<"div">, "title">) {
  return (
    <EmptyState
      icon={SearchX}
      title={`No ${what} match`}
      description="Nothing here matches the search and filters."
      action={
        <button type="button" onClick={onClear} className={buttonVariants({ variant: "outline", size: "sm" })}>
          {clearLabel}
        </button>
      }
      {...props}
    />
  );
}
