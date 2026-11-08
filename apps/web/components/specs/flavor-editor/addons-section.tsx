"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, GripVertical, Package, Plus, Search, Settings2, X } from "lucide-react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { api } from "@/lib/api-client";
import { buttonVariants } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { ConfigureOverrideableDialog, deepMergeValues } from "@/components/specs/configure-overrideable-dialog";
import { chartRevisions, day2Api, day2Keys } from "@/lib/day2";
import { cn } from "@/lib/utils";
import type { CatalogEntry, OverrideableField, SpecAddon } from "@/types";

const keyOf = (a: { team: string; name: string }) => `${a.team}/${a.name}`;

function SortableAddonItem({
  addon,
  index,
  onRemove,
  onVersionChange,
  onConfigure,
  availableVersions,
}: {
  addon: SpecAddon;
  index: number;
  onRemove: () => void;
  onVersionChange: (version: string) => void;
  onConfigure: () => void;
  availableVersions: string[];
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: keyOf(addon) });
  const style = { transform: CSS.Transform.toString(transform), transition };
  const overrideCount = addon.overrideable?.length ?? 0;

  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`selected-addon-${addon.team}-${addon.name}`}
      className={cn(
        "flex items-center gap-3 rounded-lg border bg-card p-3 transition-shadow",
        isDragging && "z-10 shadow-lg ring-2 ring-primary/50"
      )}
    >
      <button
        {...attributes}
        {...listeners}
        type="button"
        data-testid="drag-handle"
        aria-label={`Reorder ${addon.name}`}
        className="shrink-0 cursor-grab touch-none text-muted-foreground hover:text-foreground active:cursor-grabbing"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary tabular">
        {index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{addon.name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {addon.team}
          {overrideCount > 0 && <span className="ml-2 text-primary">· {overrideCount} overrideable</span>}
        </p>
      </div>
      <button
        type="button"
        onClick={onConfigure}
        className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "h-8 shrink-0 px-2")}
        title="Configure overrideable fields"
      >
        <Settings2 className="h-4 w-4" />
      </button>
      <div className="shrink-0">
        <Combobox
          options={availableVersions.map((v) => ({ value: v, label: v }))}
          value={addon.version}
          onValueChange={(v) => v && onVersionChange(v)}
          searchPlaceholder="Search revisions…"
          emptyMessage="No revision matches."
          aria-label={`${addon.name} revision`}
          className="w-24 text-xs"
        />
      </div>
      <button
        type="button"
        onClick={onRemove}
        aria-label="Remove addon"
        className="shrink-0 text-muted-foreground transition-colors hover:text-destructive"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

function AddonCatalogCard({ addon, isSelected, onAdd }: { addon: CatalogEntry; isSelected: boolean; onAdd: (version: string) => void }) {
  // The team default (HEAD when it sets none), so a cluster inherits it without a pin
  const [selectedVersion, setSelectedVersion] = useState(addon.current_version);
  return (
    <div
      data-testid={`addon-card-${addon.team}-${addon.name}`}
      className={cn(
        "rounded-xl border bg-card p-4 transition-[border-color,box-shadow,opacity]",
        isSelected ? "border-primary/50 bg-primary/5 opacity-60" : "hover:border-primary/30 hover:shadow-md"
      )}
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/8">
            <Package className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <h4 className="truncate text-sm font-semibold">{addon.name}</h4>
            <p className="text-xs text-muted-foreground">{addon.team}</p>
          </div>
        </div>
        {isSelected && (
          <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">Added</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Combobox
          options={chartRevisions(addon).map((v) => ({ value: v, label: v }))}
          value={selectedVersion}
          onValueChange={(v) => v && setSelectedVersion(v)}
          disabled={isSelected}
          searchPlaceholder="Search revisions…"
          emptyMessage="No revision matches."
          aria-label={`${addon.name} revision`}
          className="min-w-0 flex-1 text-xs"
        />
        <button
          type="button"
          onClick={() => onAdd(selectedVersion)}
          disabled={isSelected}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-8 shrink-0", isSelected && "cursor-not-allowed opacity-50")}
        >
          <Plus className="mr-1 h-3.5 w-3.5" />
          Add
        </button>
      </div>
    </div>
  );
}

function TeamSection({
  team,
  addons,
  selected,
  onAdd,
}: {
  team: string;
  addons: CatalogEntry[];
  selected: SpecAddon[];
  onAdd: (addon: CatalogEntry, version: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  return (
    <div className="space-y-3">
      <button type="button" onClick={() => setExpanded((v) => !v)} className="group flex w-full items-center gap-2 text-left">
        {expanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
        <span className="text-sm font-semibold transition-colors group-hover:text-primary">{team}</span>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">{addons.length}</span>
      </button>
      {expanded && (
        <div className="grid gap-3 pl-6 sm:grid-cols-2">
          {addons.map((addon) => (
            <AddonCatalogCard
              key={keyOf(addon)}
              addon={addon}
              isSelected={selected.some((s) => s.team === addon.team && s.name === addon.name)}
              onAdd={(version) => onAdd(addon, version)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Part 3: the day2 charts every cluster of the flavor gets, in install
 * order, each at a revision and with the fields a cluster may override.
 */
export function AddonsSection({ addons, onChange }: { addons: SpecAddon[]; onChange: (addons: SpecAddon[]) => void }) {
  const [search, setSearch] = useState("");
  const [configuring, setConfiguring] = useState<{ team: string; name: string } | null>(null);

  const { data: catalog, isLoading, error } = useQuery<CatalogEntry[]>({
    queryKey: day2Keys.catalog,
    queryFn: () => api.get<CatalogEntry[]>(day2Api.catalog),
    staleTime: 120_000,
  });
  const catalogByKey = useMemo(() => new Map((catalog ?? []).map((a) => [keyOf(a), a])), [catalog]);
  const byTeam = useMemo(() => {
    const query = search.trim().toLowerCase();
    const matching = (catalog ?? []).filter(
      (a) => !query || a.name.toLowerCase().includes(query) || a.team.toLowerCase().includes(query)
    );
    return matching.reduce<Record<string, CatalogEntry[]>>((acc, a) => {
      (acc[a.team] ??= []).push(a);
      return acc;
    }, {});
  }, [catalog, search]);

  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = addons.findIndex((a) => keyOf(a) === active.id);
    const to = addons.findIndex((a) => keyOf(a) === over.id);
    onChange(arrayMove(addons, from, to));
  };

  const configuringAddon = configuring ? addons.find((a) => keyOf(a) === keyOf(configuring)) : undefined;
  const configuringEntry = configuring ? catalogByKey.get(keyOf(configuring)) : undefined;
  // The chart's own values at the chosen revision (the team values merge on top)
  const configuringVersion = configuringAddon?.version ?? configuringEntry?.current_version ?? "HEAD";
  const { data: chartValues, isLoading: chartLoading } = useQuery<Record<string, unknown>>({
    queryKey: day2Keys.chartDefaults(configuring?.team ?? "", configuring?.name ?? "", configuringVersion),
    queryFn: () => api.get<Record<string, unknown>>(day2Api.chartDefaults(configuring!.team, configuring!.name, configuringVersion)),
    enabled: Boolean(configuring),
    staleTime: 300_000,
  });
  const defaultValues = chartValues
    ? deepMergeValues(chartValues, configuringEntry?.default_values ?? {})
    : (configuringEntry?.default_values ?? {});

  const saveOverrideable = (fields: OverrideableField[]) => {
    if (!configuring) return;
    onChange(addons.map((a) => (keyOf(a) === keyOf(configuring) ? { ...a, overrideable: fields } : a)));
    setConfiguring(null);
  };

  if (isLoading) return <Skeleton className="h-64 rounded-xl" />;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="min-w-0 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">Available</h3>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <input
              type="text"
              placeholder="Search..."
              aria-label="Search addons"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-44 rounded-lg border bg-background py-1.5 pl-8 pr-3 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30"
            />
          </div>
        </div>
        {error ? (
          <ProblemList error={error} title="The chart catalog could not be read" />
        ) : (
          <div className="max-h-[500px] space-y-6 overflow-y-auto pr-2">
            {Object.keys(byTeam).length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {search ? "No addons match your search" : "No addons available"}
              </p>
            ) : (
              Object.entries(byTeam)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([team, list]) => (
                  <TeamSection
                    key={team}
                    team={team}
                    addons={list}
                    selected={addons}
                    onAdd={(addon, version) => onChange([...addons, { team: addon.team, name: addon.name, version, overrideable: [] }])}
                  />
                ))
            )}
          </div>
        )}
      </div>

      <div className="min-w-0 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Selected Addons ({addons.length})</h3>
          {addons.length > 1 && <span className="text-xs text-muted-foreground">Drag to set the install order</span>}
        </div>
        {addons.length === 0 ? (
          <div className="rounded-xl border border-dashed p-8 text-center">
            <Package className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" aria-hidden />
            <p className="text-sm text-muted-foreground">No addons selected</p>
            <p className="mt-1 text-xs text-muted-foreground">Add a chart to install it on every cluster of the flavor.</p>
          </div>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={addons.map(keyOf)} strategy={verticalListSortingStrategy}>
              <div className="space-y-2">
                {addons.map((addon, index) => (
                  <SortableAddonItem
                    key={keyOf(addon)}
                    addon={addon}
                    index={index}
                    onRemove={() => onChange(addons.filter((a) => keyOf(a) !== keyOf(addon)))}
                    onVersionChange={(v) => onChange(addons.map((a) => (keyOf(a) === keyOf(addon) ? { ...a, version: v } : a)))}
                    onConfigure={() => setConfiguring({ team: addon.team, name: addon.name })}
                    availableVersions={chartRevisions(catalogByKey.get(keyOf(addon)), addon.version)}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </div>

      {configuring && (
        <ConfigureOverrideableDialog
          key={keyOf(configuring)}
          open={true}
          onOpenChange={(open) => !open && setConfiguring(null)}
          addonName={configuring.name}
          defaultValues={defaultValues}
          isLoadingValues={chartLoading}
          currentOverrideable={configuringAddon?.overrideable ?? []}
          onSave={saveOverrideable}
        />
      )}
    </div>
  );
}
