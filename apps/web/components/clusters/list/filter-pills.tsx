"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** One pill: its value, its words, and how many rows it shows (left out on All). */
export interface FilterPill<V extends string> {
  value: V;
  label: string;
  count?: number;
}

/**
 * The clusters list's filter style: pills under a label, one pressed at a
 * time. `children` follow the pills (a mark saying why a count is unknown).
 */
export function FilterPills<V extends string>({
  label,
  pills,
  value,
  onChange,
  testId,
  children,
}: {
  label: string;
  pills: readonly FilterPill<V>[];
  value: V;
  onChange: (next: V) => void;
  /** Each pill is `<testId>-<value>`. */
  testId?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label={`${label} filters`}>
      <span className="text-xs text-muted-foreground font-medium">{label}:</span>
      {pills.map((pill) => (
        <button
          key={pill.value}
          type="button"
          onClick={() => onChange(pill.value)}
          aria-pressed={value === pill.value}
          data-testid={testId && `${testId}-${pill.value}`}
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-all border",
            value === pill.value
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-card text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
          )}
        >
          {pill.label}
          {pill.count !== undefined && <span className="tabular-nums opacity-70">{pill.count}</span>}
        </button>
      ))}
      {children}
    </div>
  );
}
