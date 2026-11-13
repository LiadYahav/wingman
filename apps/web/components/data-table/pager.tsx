"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Previous, "Page X of Y", Next, under a paged table (server-scan's pager):
 * the caller pages its rows (a pure `paginate`) and keeps the page where it
 * keeps its other state, often the URL.
 */
export function Pager({ page, pageCount, onPage }: { page: number; pageCount: number; onPage: (page: number) => void }) {
  const button = cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1 disabled:opacity-40");
  return (
    <nav aria-label="Pages" className="flex items-center gap-3 text-sm">
      <button type="button" className={button} disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
        Previous
      </button>
      <span className="tabular-nums text-muted-foreground" data-testid="pager-status">
        Page {page} of {pageCount}
      </span>
      <button type="button" className={button} disabled={page >= pageCount} onClick={() => onPage(page + 1)}>
        Next
        <ChevronRight aria-hidden className="h-3.5 w-3.5" />
      </button>
    </nav>
  );
}
