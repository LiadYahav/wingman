import { cn } from "@/lib/utils";

/**
 * The levels of an add-on's values, lowest first, as the user names them
 * (ADR-0043's 2026-11-13 amendment): the chart's own values, the Sig values
 * (`operators/<chart>/values.yaml` in the team's repo), and the values a
 * cluster gets where the add-on is used (create, a flavor, its charts page).
 */
const VALUES_LEVELS = ["Chart values", "Sig values", "Cluster values"] as const;
export type ValuesLevel = (typeof VALUES_LEVELS)[number];

/** One compact line: the levels, `current` marked, and the file it is in. */
export function ValuesLevels({ current, path, className }: { current: ValuesLevel; path?: string; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs", className)} data-testid="values-levels">
      <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-muted-foreground" aria-label="Values, lowest first">
        {VALUES_LEVELS.map((level, i) => (
          <li key={level} className="flex items-center gap-1.5">
            {i > 0 && (
              <span aria-hidden className="text-muted-foreground/60">
                →
              </span>
            )}
            <span
              aria-current={level === current ? "true" : undefined}
              className={cn(level === current && "rounded-md bg-primary/10 px-1.5 py-px font-medium text-primary dark:bg-primary/20")}
            >
              {level}
            </span>
          </li>
        ))}
      </ol>
      {path && <code className="min-w-0 break-all font-mono text-[11px] text-muted-foreground/80">{path}</code>}
    </div>
  );
}
