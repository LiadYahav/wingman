"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Package, Search, ChevronDown, ChevronRight, Tag, AlignJustify, Code2, RefreshCw, ChevronsUpDown } from "lucide-react";
import { api } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import jsYaml from "js-yaml";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { buttonVariants } from "@/components/ui/button";
import type { AddonCatalogEntry } from "@/types";

type ViewMode = "form" | "yaml";

function ViewToggle({ mode, onChange }: { mode: ViewMode; onChange: (m: ViewMode) => void }) {
  return (
    <div className="flex items-center rounded-lg border bg-muted/40 p-0.5 gap-0.5">
      <button
        onClick={() => onChange("form")}
        className={cn(
          "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
          mode === "form"
            ? "bg-background shadow-sm text-foreground"
            : "text-muted-foreground hover:text-foreground"
        )}
      >
        <AlignJustify className="h-3 w-3" />
        Form
      </button>
      <button
        onClick={() => onChange("yaml")}
        className={cn(
          "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
          mode === "yaml"
            ? "bg-background shadow-sm text-foreground"
            : "text-muted-foreground hover:text-foreground"
        )}
      >
        <Code2 className="h-3 w-3" />
        YAML
      </button>
    </div>
  );
}

function AddonValuesDialog({
  addon,
  open,
  onOpenChange,
}: {
  addon: AddonCatalogEntry;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [viewMode, setViewMode] = useState<ViewMode>("form");
  const hasValues = Object.keys(addon.default_values ?? {}).length > 0;
  const yamlText = hasValues
    ? jsYaml.dump(addon.default_values, { indent: 2, lineWidth: -1 })
    : "";

  // Flatten nested object to dot-path entries for form view
  function flattenForDisplay(obj: Record<string, unknown>, prefix = ""): [string, unknown][] {
    const out: [string, unknown][] = [];
    for (const [k, v] of Object.entries(obj)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (v !== null && typeof v === "object" && !Array.isArray(v)) {
        out.push(...flattenForDisplay(v as Record<string, unknown>, key));
      } else {
        out.push([key, v]);
      }
    }
    return out;
  }

  const flatEntries = hasValues ? flattenForDisplay(addon.default_values ?? {}) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl w-[95vw]">
        <DialogHeader>
          <div className="flex items-center justify-between pr-8">
            <div>
              <DialogTitle>{addon.name} — Team Default Values</DialogTitle>
              <DialogDescription>
                Team: <strong>{addon.team}</strong> · Version: <strong>{addon.current_version}</strong>
              </DialogDescription>
            </div>
            {hasValues && <ViewToggle mode={viewMode} onChange={setViewMode} />}
          </div>
        </DialogHeader>

        {/* Single overflow-auto container: horizontal scrollbar stays anchored to the
            bottom edge of the visible box, not the bottom of the content */}
        <div className="max-h-[65vh] overflow-auto">
          {!hasValues ? (
            <p className="text-sm text-muted-foreground italic py-4 text-center">No default values configured</p>
          ) : viewMode === "yaml" ? (
            <pre className="rounded-lg bg-muted/50 border p-4 text-xs font-mono leading-relaxed whitespace-pre">
              {yamlText}
            </pre>
          ) : (
            <table className="text-xs w-full border-collapse" style={{ minWidth: "max-content" }}>
              <thead>
                <tr className="bg-muted/30">
                  <th className="text-left px-3 py-2 font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap border-b">Key</th>
                  <th className="text-left px-3 py-2 font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap border-b">Default Value</th>
                </tr>
              </thead>
              <tbody>
                {flatEntries.map(([key, value]) => (
                  <tr key={key} className="hover:bg-muted/20 transition-colors border-b border-border/50 last:border-0">
                    <td className="px-3 py-2 font-mono text-foreground font-medium whitespace-nowrap align-top">{key}</td>
                    <td className="px-3 py-2 font-mono text-muted-foreground break-all">
                      {value === null ? (
                        <span className="italic text-muted-foreground/60">null</span>
                      ) : typeof value === "boolean" ? (
                        <span className={value ? "text-status-ready" : "text-status-error"}>{String(value)}</span>
                      ) : (
                        String(value)
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <DialogFooter showCloseButton />
      </DialogContent>
    </Dialog>
  );
}

function AddonCard({ addon }: { addon: AddonCatalogEntry }) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const defaultEntries = Object.entries(addon.default_values ?? {});

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        onClick={() => setDialogOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setDialogOpen(true); }}
        className="bg-card rounded-xl border shadow-sm hover:shadow-md hover:border-primary/30 transition-all cursor-pointer text-left"
      >
        <div className="p-4 space-y-2.5">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/8 dark:bg-primary/15 shrink-0">
                <Package className="h-4 w-4 text-primary" />
              </div>
              <h3 className="text-sm font-semibold truncate">{addon.name}</h3>
            </div>
            <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs bg-primary/8 text-primary dark:bg-primary/20 font-medium shrink-0">
              <Tag className="h-2.5 w-2.5" />{addon.current_version}
            </span>
          </div>

          {addon.argocd_metadata && (
            <p className="text-xs text-muted-foreground truncate" title={addon.argocd_metadata.repourl}>
              {addon.argocd_metadata.repourl.replace(/^https?:\/\//, "")}
            </p>
          )}

          {addon.available_versions.length > 1 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-muted-foreground">Versions:</span>
              {addon.available_versions.slice(0, 3).map((v) => (
                <span
                  key={v}
                  className={cn(
                    "rounded-full px-1.5 py-0.5 text-xs font-medium",
                    v === addon.current_version
                      ? "bg-primary/8 text-primary dark:bg-primary/20"
                      : "bg-muted text-muted-foreground"
                  )}
                >
                  {v}
                </span>
              ))}
              {addon.available_versions.length > 3 && (
                <span className="text-xs text-muted-foreground">+{addon.available_versions.length - 3} more</span>
              )}
            </div>
          )}

          <p className="text-xs text-primary/70 font-medium pt-0.5">
            {defaultEntries.length > 0
              ? `${defaultEntries.length} default value${defaultEntries.length !== 1 ? "s" : ""} — click to view`
              : "Click to view details"}
          </p>
        </div>
      </div>

      <AddonValuesDialog addon={addon} open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  );
}

function TeamSection({ team, addons }: { team: string; addons: AddonCatalogEntry[] }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="space-y-3">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 group w-full text-left"
      >
        {expanded
          ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
          : <ChevronRight className="h-4 w-4 text-muted-foreground" />
        }
        <span className="text-sm font-semibold group-hover:text-primary transition-colors">{team}</span>
        <span className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground font-medium">
          {addons.length}
        </span>
      </button>

      {expanded && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 pl-6">
          {addons.map((addon) => (
            <AddonCard key={`${addon.team}-${addon.name}`} addon={addon} />
          ))}
        </div>
      )}
    </div>
  );
}

type AddonSort = "name-asc" | "name-desc" | "team-asc";

export default function AddonsPage() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<AddonSort>("name-asc");
  const queryClient = useQueryClient();

  const { data: addons, isLoading, isFetching, error } = useQuery<AddonCatalogEntry[]>({
    queryKey: ["addons", "catalog"],
    queryFn: () => api.get<AddonCatalogEntry[]>("/api/day2/addons"),
    staleTime: 120_000,
  });

  const filtered = (addons?.filter((a) =>
    search.trim() === "" ||
    a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.team.toLowerCase().includes(search.toLowerCase())
  ) ?? []).sort((a, b) => {
    if (sort === "name-asc") return a.name.localeCompare(b.name);
    if (sort === "name-desc") return b.name.localeCompare(a.name);
    if (sort === "team-asc") return a.team.localeCompare(b.team) || a.name.localeCompare(b.name);
    return 0;
  });

  const byTeam = filtered.reduce<Record<string, AddonCatalogEntry[]>>((acc, addon) => {
    if (!acc[addon.team]) acc[addon.team] = [];
    acc[addon.team].push(addon);
    return acc;
  }, {});

  const totalAddons = addons?.length ?? 0;
  const totalTeams = Object.keys(byTeam).length;

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            Addon Catalog
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {isLoading
              ? "Loading catalog..."
              : `${totalAddons} addon${totalAddons !== 1 ? "s" : ""} across ${totalTeams} team${totalTeams !== 1 ? "s" : ""}`}
          </p>
        </div>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ["addons", "catalog"] })}
          disabled={isFetching}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
          title="Refresh catalog"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Search + Sort */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-40 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search addons or teams..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border bg-card pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground" />
          <div className="flex items-center rounded-lg border bg-muted/40 p-0.5 gap-0.5">
            {([["name-asc", "A→Z"], ["name-desc", "Z→A"], ["team-asc", "Team"]] as [AddonSort, string][]).map(([v, label]) => (
              <button key={v} onClick={() => setSort(v)}
                className={cn("rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                  sort === v ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
              >{label}</button>
            ))}
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load addon catalog. Please try again.
        </div>
      ) : isLoading ? (
        <div className="space-y-6">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="space-y-3">
              <Skeleton className="h-5 w-32" />
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 3 }).map((_, j) => (
                  <Skeleton key={j} className="h-28 rounded-xl" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : Object.keys(byTeam).length === 0 ? (
        <div className="bg-card rounded-xl border shadow-sm p-16 text-center">
          <Package className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm font-semibold">
            {search ? "No addons match your search" : "No addons found"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {search ? "Try a different search term" : "Addon definitions will appear here once configured in the day2 repo"}
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {Object.entries(byTeam)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([team, teamAddons]) => (
              <TeamSection key={team} team={team} addons={teamAddons} />
            ))}
        </div>
      )}
    </div>
  );
}
