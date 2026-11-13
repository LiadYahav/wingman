"use client";

import type { ReactNode } from "react";
import { Check, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * One checkable line in a table popover (the column picker, a column's value
 * filter): the whole line is the checkbox. `checked="mixed"` for a "Select
 * all" that some, not all, of its lines are.
 */
export function CheckItem({
  checked,
  onToggle,
  disabled,
  className,
  children,
}: {
  checked: boolean | "mixed";
  onToggle: () => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const on = checked !== false;
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
    >
      <span
        aria-hidden
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
          on ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"
        )}
      >
        {checked === "mixed" ? <Minus className="h-3 w-3" strokeWidth={3} /> : on && <Check className="h-3 w-3" strokeWidth={3} />}
      </span>
      <span className="min-w-0 flex-1 truncate">{children}</span>
    </button>
  );
}
