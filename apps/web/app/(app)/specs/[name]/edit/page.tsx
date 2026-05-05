"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  ArrowLeft,
  Eye,
  Package,
  Search,
  ChevronDown,
  ChevronRight,
  Plus,
  X,
  GripVertical,
  Tag,
} from "lucide-react";
import { toast } from "sonner";
import jsYaml from "js-yaml";
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
import { Skeleton } from "@/components/ui/skeleton";
import { ReviewDialog } from "@/components/common/review-dialog";
import { computeLineDiff } from "@/lib/diff";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ClusterSpec, MRDetail, AddonCatalogEntry, SpecAddon } from "@/types";

// ── Sortable Addon Item ───────────────────────────────────────────────────────

function SortableAddonItem({
  addon,
  index,
  onRemove,
  onVersionChange,
  availableVersions,
}: {
  addon: SpecAddon;
  index: number;
  onRemove: () => void;
  onVersionChange: (version: string) => void;
  availableVersions: string[];
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: `${addon.team}/${addon.name}` });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "flex items-center gap-3 rounded-lg border bg-card p-3 transition-shadow",
        isDragging && "shadow-lg ring-2 ring-primary/50 z-10"
      )}
    >
      <button
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground touch-none"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary shrink-0">
        {index + 1}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{addon.name}</p>
        <p className="text-xs text-muted-foreground">{addon.team}</p>
      </div>
      <Select
        value={addon.version}
        onValueChange={(v) => v && onVersionChange(v)}
      >
        <SelectTrigger className="w-24 h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {availableVersions.map((v) => (
            <SelectItem key={v} value={v}>
              {v}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <button
        onClick={onRemove}
        className="text-muted-foreground hover:text-destructive transition-colors"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

// ── Addon Catalog Card ────────────────────────────────────────────────────────

function AddonCatalogCard({
  addon,
  isSelected,
  onAdd,
}: {
  addon: AddonCatalogEntry;
  isSelected: boolean;
  onAdd: (version: string) => void;
}) {
  const [selectedVersion, setSelectedVersion] = useState(addon.current_version);

  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-4 transition-all",
        isSelected
          ? "border-primary/50 bg-primary/5 opacity-60"
          : "hover:shadow-md hover:border-primary/30"
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/8 shrink-0">
            <Package className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-semibold truncate">{addon.name}</h4>
            <p className="text-xs text-muted-foreground">{addon.team}</p>
          </div>
        </div>
        {isSelected && (
          <span className="rounded-full px-2 py-0.5 text-xs bg-primary/10 text-primary font-medium shrink-0">
            Added
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Select
          value={selectedVersion}
          onValueChange={(v) => v && setSelectedVersion(v)}
          disabled={isSelected}
        >
          <SelectTrigger className="flex-1 h-8 text-xs">
            <Tag className="h-3 w-3 mr-1" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            {addon.available_versions.map((v) => (
              <SelectItem key={v} value={v}>
                {v}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <button
          onClick={() => onAdd(selectedVersion)}
          disabled={isSelected}
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            "h-8 shrink-0",
            isSelected && "opacity-50 cursor-not-allowed"
          )}
        >
          <Plus className="h-3.5 w-3.5 mr-1" />
          Add
        </button>
      </div>
    </div>
  );
}

// ── Team Section ──────────────────────────────────────────────────────────────

function TeamSection({
  team,
  addons,
  selectedAddons,
  onAdd,
}: {
  team: string;
  addons: AddonCatalogEntry[];
  selectedAddons: SpecAddon[];
  onAdd: (addon: AddonCatalogEntry, version: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);

  const isAddonSelected = (addon: AddonCatalogEntry) =>
    selectedAddons.some((s) => s.team === addon.team && s.name === addon.name);

  return (
    <div className="space-y-3">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 group w-full text-left"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
        <span className="text-sm font-semibold group-hover:text-primary transition-colors">
          {team}
        </span>
        <span className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground font-medium">
          {addons.length}
        </span>
      </button>

      {expanded && (
        <div className="grid gap-3 sm:grid-cols-2 pl-6">
          {addons.map((addon) => (
            <AddonCatalogCard
              key={`${addon.team}-${addon.name}`}
              addon={addon}
              isSelected={isAddonSelected(addon)}
              onAdd={(version) => onAdd(addon, version)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function EditSpecPage() {
  const params = useParams();
  const specName = params.name as string;
  const router = useRouter();

  // Day1 YAML state
  const [day1Yaml, setDay1Yaml] = useState<string | null>(null);

  // Day2 addons state
  const [selectedAddons, setSelectedAddons] = useState<SpecAddon[] | null>(null);

  // UI state
  const [reviewOpen, setReviewOpen] = useState(false);
  const [addonSearch, setAddonSearch] = useState("");

  // Fetch spec
  const { data: spec, isLoading: specLoading } = useQuery<ClusterSpec>({
    queryKey: ["specs", specName],
    queryFn: () => api.get<ClusterSpec>(`/api/day1/specs/${specName}`),
    staleTime: 60_000,
  });

  // Fetch addon catalog
  const { data: addonCatalog, isLoading: catalogLoading } = useQuery<
    AddonCatalogEntry[]
  >({
    queryKey: ["addons", "catalog"],
    queryFn: () => api.get<AddonCatalogEntry[]>("/api/day2/addons"),
    staleTime: 120_000,
  });

  // Initialize state from spec
  const originalDay1Yaml = useMemo(() => {
    if (!spec) return "";
    const day1Only = {
      apiVersion: spec.apiVersion,
      kind: spec.kind,
      metadata: spec.metadata,
      spec: { day1: spec.spec.day1 },
    };
    return jsYaml.dump(day1Only, { lineWidth: 120, quotingType: '"' });
  }, [spec]);

  const effectiveDay1Yaml = day1Yaml ?? originalDay1Yaml;
  const effectiveAddons = selectedAddons ?? spec?.spec.day2.addons ?? [];

  // Build addon version lookup from catalog
  const addonVersionsMap = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const addon of addonCatalog ?? []) {
      map[`${addon.team}/${addon.name}`] = addon.available_versions;
    }
    return map;
  }, [addonCatalog]);

  // Filter and group addons
  const filteredCatalog = useMemo(() => {
    if (!addonCatalog) return {};
    const filtered = addonCatalog.filter(
      (a) =>
        addonSearch.trim() === "" ||
        a.name.toLowerCase().includes(addonSearch.toLowerCase()) ||
        a.team.toLowerCase().includes(addonSearch.toLowerCase())
    );
    return filtered.reduce<Record<string, AddonCatalogEntry[]>>((acc, addon) => {
      if (!acc[addon.team]) acc[addon.team] = [];
      acc[addon.team].push(addon);
      return acc;
    }, {});
  }, [addonCatalog, addonSearch]);

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // DnD handler
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = effectiveAddons.findIndex(
        (a) => `${a.team}/${a.name}` === active.id
      );
      const newIndex = effectiveAddons.findIndex(
        (a) => `${a.team}/${a.name}` === over.id
      );
      setSelectedAddons(arrayMove(effectiveAddons, oldIndex, newIndex));
    }
  };

  // Add addon
  const handleAddAddon = (addon: AddonCatalogEntry, version: string) => {
    const newAddon: SpecAddon = {
      team: addon.team,
      name: addon.name,
      version,
      overrides: {},
    };
    setSelectedAddons([...effectiveAddons, newAddon]);
  };

  // Remove addon
  const handleRemoveAddon = (team: string, name: string) => {
    setSelectedAddons(effectiveAddons.filter((a) => !(a.team === team && a.name === name)));
  };

  // Change addon version
  const handleVersionChange = (team: string, name: string, version: string) => {
    setSelectedAddons(
      effectiveAddons.map((a) =>
        a.team === team && a.name === name ? { ...a, version } : a
      )
    );
  };

  // Build final spec for save
  const buildFinalSpec = (): ClusterSpec => {
    let day1Parsed: unknown;
    try {
      day1Parsed = jsYaml.load(effectiveDay1Yaml);
    } catch (e) {
      throw new Error(`Invalid Day1 YAML: ${(e as Error).message}`);
    }

    const day1Spec = day1Parsed as {
      apiVersion: string;
      kind: string;
      metadata: ClusterSpec["metadata"];
      spec: { day1: ClusterSpec["spec"]["day1"] };
    };

    return {
      apiVersion: day1Spec.apiVersion,
      kind: day1Spec.kind,
      metadata: day1Spec.metadata,
      spec: {
        day1: day1Spec.spec.day1,
        day2: {
          addons: effectiveAddons,
        },
      },
    };
  };

  // Compute diff for review
  const originalFullYaml = useMemo(() => {
    if (!spec) return "";
    return jsYaml.dump(spec, { lineWidth: 120, quotingType: '"' });
  }, [spec]);

  const currentFullYaml = useMemo(() => {
    try {
      const day1Parsed = jsYaml.load(effectiveDay1Yaml) as {
        apiVersion: string;
        kind: string;
        metadata: ClusterSpec["metadata"];
        spec: { day1: ClusterSpec["spec"]["day1"] };
      };
      const fullSpec: ClusterSpec = {
        apiVersion: day1Parsed.apiVersion,
        kind: day1Parsed.kind,
        metadata: day1Parsed.metadata,
        spec: {
          day1: day1Parsed.spec.day1,
          day2: { addons: effectiveAddons },
        },
      };
      return jsYaml.dump(fullSpec, { lineWidth: 120, quotingType: '"' });
    } catch {
      return "";
    }
  }, [effectiveDay1Yaml, effectiveAddons]);

  const diff = useMemo(
    () => computeLineDiff(originalFullYaml, currentFullYaml),
    [originalFullYaml, currentFullYaml]
  );

  // Save mutation
  const updateMutation = useMutation({
    mutationFn: async () => {
      const finalSpec = buildFinalSpec();
      return api.put<MRDetail>(`/api/day1/specs/${specName}`, finalSpec);
    },
    onSuccess: (mr) => {
      toast.success(`Update MR #${mr.iid} created: ${mr.title}`);
      setReviewOpen(false);
      router.push(`/specs/${specName}`);
    },
    onError: (err: Error) => {
      toast.error(`Failed: ${err.message}`);
      setReviewOpen(false);
    },
  });

  const handleReview = () => {
    try {
      buildFinalSpec();
    } catch (e) {
      toast.error((e as Error).message);
      return;
    }
    setReviewOpen(true);
  };

  const isLoading = specLoading || catalogLoading;

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          href={`/specs/${specName}`}
          className={buttonVariants({ variant: "ghost", size: "icon" })}
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            Edit Spec
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Editing <span className="font-medium">{specName}</span>
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-6">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
        </div>
      ) : (
        <>
          {/* Day1 Section */}
          <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/20">
              <span className="text-sm font-semibold">Day 1 — Cluster Template</span>
              <span className="text-xs text-muted-foreground">
                Variables and template configuration
              </span>
            </div>
            <textarea
              className="w-full font-mono text-xs bg-zinc-950 text-zinc-200 p-4 min-h-[300px] focus:outline-none resize-y leading-5"
              value={effectiveDay1Yaml}
              onChange={(e) => setDay1Yaml(e.target.value)}
              spellCheck={false}
            />
          </div>

          {/* Day2 Section */}
          <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b bg-muted/20">
              <span className="text-sm font-semibold">Day 2 — Addons</span>
              <p className="text-xs text-muted-foreground mt-0.5">
                Select addons and drag to set install order
              </p>
            </div>

            <div className="p-4 grid lg:grid-cols-2 gap-6">
              {/* Left: Available Addons */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Available Addons</h3>
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="Search..."
                      value={addonSearch}
                      onChange={(e) => setAddonSearch(e.target.value)}
                      className="w-40 rounded-lg border bg-background pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                  </div>
                </div>

                <div className="max-h-[500px] overflow-y-auto space-y-6 pr-2">
                  {Object.keys(filteredCatalog).length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-8">
                      {addonSearch ? "No addons match your search" : "No addons available"}
                    </p>
                  ) : (
                    Object.entries(filteredCatalog)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([team, addons]) => (
                        <TeamSection
                          key={team}
                          team={team}
                          addons={addons}
                          selectedAddons={effectiveAddons}
                          onAdd={handleAddAddon}
                        />
                      ))
                  )}
                </div>
              </div>

              {/* Right: Selected Addons */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">
                    Selected Addons ({effectiveAddons.length})
                  </h3>
                  <span className="text-xs text-muted-foreground">
                    Drag to reorder
                  </span>
                </div>

                {effectiveAddons.length === 0 ? (
                  <div className="rounded-xl border-2 border-dashed p-8 text-center">
                    <Package className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">
                      No addons selected
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Click &ldquo;Add&rdquo; on an addon to include it
                    </p>
                  </div>
                ) : (
                  <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragEnd={handleDragEnd}
                  >
                    <SortableContext
                      items={effectiveAddons.map((a) => `${a.team}/${a.name}`)}
                      strategy={verticalListSortingStrategy}
                    >
                      <div className="space-y-2">
                        {effectiveAddons.map((addon, index) => (
                          <SortableAddonItem
                            key={`${addon.team}/${addon.name}`}
                            addon={addon}
                            index={index}
                            onRemove={() => handleRemoveAddon(addon.team, addon.name)}
                            onVersionChange={(v) =>
                              handleVersionChange(addon.team, addon.name, v)
                            }
                            availableVersions={
                              addonVersionsMap[`${addon.team}/${addon.name}`] ?? [
                                addon.version,
                              ]
                            }
                          />
                        ))}
                      </div>
                    </SortableContext>
                  </DndContext>
                )}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <Link
              href={`/specs/${specName}`}
              className={buttonVariants({ variant: "outline" })}
            >
              Cancel
            </Link>
            <button
              onClick={handleReview}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
            >
              <Eye className="h-4 w-4" />
              Review & Update
            </button>
          </div>
        </>
      )}

      {/* Review Dialog */}
      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title={`Review: Update Spec "${specName}"`}
        description={
          diff
            ? "Changed lines are highlighted below. Green = added, red = removed."
            : "No changes detected."
        }
        diff={diff || undefined}
        onConfirm={() => updateMutation.mutate()}
        isPending={updateMutation.isPending}
        confirmLabel="Confirm — Update Spec MR"
      >
        {!diff && (
          <p className="text-sm text-muted-foreground italic text-center py-4">
            Nothing changed.
          </p>
        )}
      </ReviewDialog>
    </div>
  );
}
