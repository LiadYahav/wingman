"use client";

import { ChevronDown } from "lucide-react";
import { CheckItem } from "@/components/data-table/check-item";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/**
 * A filter dropdown that takes one value, several, or none (all), as
 * server-scan's (team-redbull/server-scan at 92146d3,
 * `frontend/src/features/inventory/MultiSelect.tsx`, decision 18): a button
 * showing the choice ("All (3,104)", "Dell, HPE", "3 selected") and a
 * checklist, each option with how many servers ticking it would show.
 */

export interface MultiSelectOption {
  value: string;
  label: string;
  /** Servers this option would show under every other filter; omitted until the fleet loads. */
  count?: number;
}

/** The button's text for the current choice. */
function summary(options: MultiSelectOption[], selected: string[], allLabel: string): string {
  if (selected.length === 0) return allLabel;
  const labels = selected.map((value) => options.find((o) => o.value === value)?.label ?? value);
  return labels.length <= 2 ? labels.join(", ") : `${labels.length} selected`;
}

export function MultiSelect({
  label,
  options,
  selected,
  onToggle,
  onClear,
  allLabel,
}: {
  label: string;
  options: MultiSelectOption[];
  selected: string[];
  onToggle: (value: string) => void;
  /** Back to "all". */
  onClear: () => void;
  /** The button's text while nothing is ticked. */
  allLabel: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      <Popover>
        <PopoverTrigger
          aria-label={`${label}: ${summary(options, selected, allLabel)}`}
          data-testid={`ss-filter-${label.toLowerCase()}`}
          className={cn(
            "flex h-8 w-full min-w-0 items-center justify-between gap-2 rounded-lg border bg-card px-2.5 text-left text-sm font-normal text-foreground outline-none transition-colors hover:border-foreground/30 focus-visible:ring-2 focus-visible:ring-ring/50",
            selected.length > 0 && "border-primary/50"
          )}
        >
          <span className="min-w-0 truncate">{summary(options, selected, allLabel)}</span>
          <ChevronDown aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-max min-w-48 max-w-[22rem] gap-0 p-1.5" aria-label={`${label} options`}>
          {selected.length > 0 && (
            <button type="button" onClick={onClear} className="w-full rounded-md px-2 py-1 text-left text-xs text-primary hover:bg-muted">
              Clear (show all)
            </button>
          )}
          <div role="group" aria-label={`${label} values`} className="max-h-72 overflow-y-auto">
            {options.map((option) => (
              <CheckItem key={option.value} checked={selected.includes(option.value)} onToggle={() => onToggle(option.value)}>
                <span className="flex items-center justify-between gap-3">
                  <span>{option.label}</span>
                  {option.count !== undefined && <span className="tabular-nums text-xs text-muted-foreground">{option.count}</span>}
                </span>
              </CheckItem>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
