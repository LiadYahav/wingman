import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * "Rows: 10 20 50", shown once a list has more than 10 rows. The list pages
 * go back to page 1 on a new size (their `onPageSize`).
 */
export function PageSizePicker({
  total,
  sizes,
  pageSize,
  onPageSize,
}: {
  total: number;
  sizes: readonly number[];
  pageSize: number;
  onPageSize: (size: number) => void;
}) {
  if (total <= 10) return null;
  return (
    <div className="flex items-center gap-1.5 ml-auto">
      <span className="text-xs text-muted-foreground">Rows:</span>
      <div className="flex items-center rounded-lg border bg-muted/40 p-0.5 gap-0.5">
        {sizes.map((n) => (
          <button
            key={n}
            onClick={() => onPageSize(n)}
            className={cn(
              "rounded-md px-2 py-0.5 text-xs font-medium transition-all",
              pageSize === n
                ? "bg-background shadow-sm text-foreground"
                : "text-muted-foreground hover:text-foreground"
            )}
          >{n}</button>
        ))}
      </div>
    </div>
  );
}

/**
 * "Showing 21–40 of 95" and the page buttons: Prev, the first and last page
 * and the ones beside the current one (gaps as "…"), Next. Nothing when the
 * list fits on one page.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;
  const visible = Array.from({ length: totalPages }, (_, i) => i + 1).filter(
    (p) => p === 1 || p === totalPages || Math.abs(p - page) <= 1
  );
  const withGaps: (number | "...")[] = [];
  let prev = 0;
  for (const p of visible) {
    if (p - prev > 1) withGaps.push("...");
    withGaps.push(p);
    prev = p;
  }
  return (
    <div className="flex items-center justify-between text-sm">
      <p className="text-xs text-muted-foreground">
        Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPage(Math.max(1, page - 1))}
          disabled={page === 1}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "px-2 py-1 h-7 text-xs disabled:opacity-40")}
        >← Prev</button>
        {withGaps.map((p, i) =>
          p === "..." ? (
            <span key={`e-${i}`} className="px-1 text-muted-foreground text-xs">…</span>
          ) : (
            <button
              key={p}
              onClick={() => onPage(p)}
              className={cn(buttonVariants({ variant: p === page ? "default" : "outline", size: "sm" }), "px-2.5 py-1 h-7 text-xs min-w-[28px]")}
            >{p}</button>
          )
        )}
        <button
          onClick={() => onPage(Math.min(totalPages, page + 1))}
          disabled={page === totalPages}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "px-2 py-1 h-7 text-xs disabled:opacity-40")}
        >Next →</button>
      </div>
    </div>
  );
}
