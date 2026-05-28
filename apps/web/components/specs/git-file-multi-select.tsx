"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, FolderOpen } from "lucide-react";
import { api } from "@/lib/api-client";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// Shape of each extra_configs item — matches the Jinja2 template list items.
export interface ConfigItem {
  name: string;
}

interface GitFileMultiSelectProps {
  value: ConfigItem[];
  onChange: (v: ConfigItem[]) => void;
  readOnly?: boolean;
}

export function GitFileMultiSelect({ value, onChange, readOnly = false }: GitFileMultiSelectProps) {
  const [search, setSearch] = useState("");

  const { data: available = [], isLoading, isError } = useQuery<string[]>({
    queryKey: ["specs", "extra-configs"],
    queryFn: () => api.get<string[]>("/api/day1/specs/extra-configs"),
    staleTime: 60_000,
  });

  const selectedNames = new Set(value.map((item) => item.name));

  const filtered = available.filter((name) =>
    name.toLowerCase().includes(search.toLowerCase())
  );

  const toggle = (name: string) => {
    if (readOnly) return;
    if (selectedNames.has(name)) {
      onChange(value.filter((item) => item.name !== name));
    } else {
      onChange([...value, { name }]);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-8 rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError || available.length === 0) {
    return (
      <div className="rounded-lg border-2 border-dashed border-border/50 p-4 text-center text-sm text-muted-foreground">
        <FolderOpen className="h-5 w-5 mx-auto mb-1.5 opacity-40" />
        {isError ? "Could not load config files." : "No config files found."}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          placeholder="Search configs…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          disabled={readOnly}
          className="w-full rounded-lg border bg-background pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 disabled:opacity-50"
        />
      </div>

      {/* Selectable list */}
      <div className="max-h-52 overflow-y-auto rounded-lg border divide-y">
        {filtered.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">No results</p>
        ) : (
          filtered.map((name) => {
            const checked = selectedNames.has(name);
            return (
              <button
                key={name}
                type="button"
                onClick={() => toggle(name)}
                disabled={readOnly}
                className={cn(
                  "flex w-full items-center gap-3 px-3 py-2 text-left transition-colors",
                  "hover:bg-muted/50 disabled:cursor-default disabled:opacity-60",
                  checked && "bg-primary/5"
                )}
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => toggle(name)}
                  disabled={readOnly}
                />
                <span className="truncate font-mono text-xs">{name}</span>
              </button>
            );
          })
        )}
      </div>

      {/* Selected summary */}
      {value.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {value.length} selected:{" "}
          <span className="font-medium text-foreground">
            {value.map((i) => i.name).join(", ")}
          </span>
        </p>
      )}
    </div>
  );
}
