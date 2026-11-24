"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Check, Search } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { DropdownChevron, dropdownTriggerClassName } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { PoolCount } from "@/types/inventory";

/** `All InfraEnvs`, the one picked, or how many (those this MCE lacks too). */
function pickedLabel(selection: readonly string[]): string {
  if (selection.length === 0) return "All InfraEnvs";
  return selection.length === 1 ? selection[0] : `${selection.length} InfraEnvs picked`;
}

/** Up and Down move between the choices, from the search box too; Up from the first returns to it. */
function moveFocus(event: KeyboardEvent<HTMLElement>, list: HTMLElement | null, search: HTMLElement | null) {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const options = [...(list?.querySelectorAll<HTMLElement>('[role="checkbox"]') ?? [])];
  if (options.length === 0) return;
  event.preventDefault();
  const at = options.indexOf(document.activeElement as HTMLElement);
  const next = event.key === "ArrowDown" ? Math.min(at + 1, options.length - 1) : at - 1;
  (next >= 0 ? options[next] : search)?.focus();
}

function Choice({ pool, checked, onToggle }: { pool: PoolCount & { infra_env: string }; checked: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={onToggle}
      data-infra-env={pool.infra_env}
      className="flex min-h-9 w-full items-center gap-2 rounded-md px-2 text-left text-sm outline-none hover:bg-accent focus-visible:bg-accent sm:min-h-8"
    >
      <span
        aria-hidden
        className={cn(
          "flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
          checked ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40 bg-background"
        )}
      >
        {checked && <Check className="size-3" strokeWidth={3} />}
      </span>
      <span className="min-w-0 flex-1 truncate font-mono text-xs">{pool.infra_env}</span>
      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{pool.available} available</span>
    </button>
  );
}

/**
 * The InfraEnvs the table shows, several at once (none: every one). The
 * choices are this MCE's InfraEnvs, found by a part of the name; the picked
 * names are kept when the MCE changes, so those another MCE lacks stay picked
 * here too, and only Clear drops them.
 */
export function InfraEnvPicker({
  mce,
  pools,
  selection,
  onChange,
}: {
  mce: string;
  pools: readonly PoolCount[];
  selection: readonly string[];
  onChange: (next: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const picked = new Set(selection);
  const named = pools.filter((pool): pool is PoolCount & { infra_env: string } => pool.infra_env !== null);
  const needle = query.trim().toLowerCase();
  const shown = needle ? named.filter((pool) => pool.infra_env.toLowerCase().includes(needle)) : named;
  const unpicked = shown.filter((pool) => !picked.has(pool.infra_env)).map((pool) => pool.infra_env);
  const toggle = (name: string) => onChange(picked.has(name) ? selection.filter((n) => n !== name) : [...selection, name]);
  const label = pickedLabel(selection);
  return (
    <Popover onOpenChange={(open) => !open && setQuery("")}>
      <PopoverTrigger
        data-size="default"
        data-testid="infra-env-picker"
        aria-label={`InfraEnvs: ${label}`}
        className={cn(dropdownTriggerClassName, "w-full sm:w-64")}
      >
        <span className={cn("min-w-0 flex-1 truncate text-left", selection.length === 1 && "font-mono text-xs")}>{label}</span>
        <DropdownChevron />
      </PopoverTrigger>
      <PopoverContent
        align="start"
        initialFocus={search}
        className="w-[min(24rem,calc(100vw-2rem))] gap-0 p-0"
        data-testid="infra-env-choices"
        aria-label={`InfraEnvs on ${mce}`}
      >
        <div className="flex items-center gap-2 border-b px-3">
          <Search aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          <input
            ref={search}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => moveFocus(event, list.current, search.current)}
            placeholder="Find an InfraEnv…"
            aria-label="Find an InfraEnv"
            className="h-9 w-full min-w-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:hidden"
          />
        </div>
        <div
          ref={list}
          role="group"
          aria-label={`InfraEnvs on ${mce}`}
          onKeyDown={(event) => moveFocus(event, list.current, search.current)}
          className="max-h-72 overflow-y-auto p-1"
        >
          {shown.map((pool) => (
            <Choice key={pool.infra_env} pool={pool} checked={picked.has(pool.infra_env)} onToggle={() => toggle(pool.infra_env)} />
          ))}
          {shown.length === 0 && <p className="px-3 py-6 text-center text-sm text-muted-foreground">No InfraEnv on this MCE matches.</p>}
        </div>
        <div className="flex items-center justify-between gap-2 border-t p-1.5">
          {needle ? (
            <button
              type="button"
              disabled={unpicked.length === 0}
              onClick={() => onChange([...selection, ...unpicked])}
              className="rounded-md px-2 py-1 text-xs font-medium text-primary outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50"
            >
              Pick the {shown.length} found
            </button>
          ) : (
            <span className="px-2 text-xs text-muted-foreground">{selection.length === 0 ? "None picked: every InfraEnv" : `${selection.length} picked`}</span>
          )}
          <button
            type="button"
            disabled={selection.length === 0}
            onClick={() => onChange([])}
            className="rounded-md px-2 py-1 text-xs text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50"
          >
            Clear
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
