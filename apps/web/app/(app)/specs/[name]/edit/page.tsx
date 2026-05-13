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
  Settings2,
  FileCode2,
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
import { ConfigureOverrideableDialog } from "@/components/specs/configure-overrideable-dialog";
import { DynamicVariableForm, initFormValues, type FormValues } from "@/components/clusters/dynamic-variable-form";
import type { ClusterSpec, MRDetail, AddonCatalogEntry, SpecAddon, OverrideableField, TemplateField } from "@/types";

// ── Sortable Addon Item ───────────────────────────────────────────────────────

function SortableAddonItem({
  addon, index, onRemove, onVersionChange, onConfigure, availableVersions,
}: {
  addon: SpecAddon; index: number; onRemove: () => void;
  onVersionChange: (v: string) => void; onConfigure: () => void; availableVersions: string[];
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: `${addon.team}/${addon.name}` });
  const style = { transform: CSS.Transform.toString(transform), transition };
  const overrideCount = addon.overrideable?.length ?? 0;

  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`selected-addon-${addon.team}-${addon.name}`}
      className={cn("flex items-center gap-3 rounded-lg border bg-card p-3 transition-shadow", isDragging && "shadow-lg ring-2 ring-primary/50 z-10")}
    >
      <button {...attributes} {...listeners} data-testid="drag-handle"
        className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground touch-none shrink-0">
        <GripVertical className="h-4 w-4" />
      </button>
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary shrink-0">
        {index + 1}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{addon.name}</p>
        <p className="text-xs text-muted-foreground truncate">
          {addon.team}
          {overrideCount > 0 && <span className="ml-2 text-primary">· {overrideCount} overrideable</span>}
        </p>
      </div>
      <button onClick={onConfigure} className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "h-8 px-2 shrink-0")}
        title="Configure overrideable fields">
        <Settings2 className="h-4 w-4" />
      </button>
      <div className="shrink-0">
        <Select value={addon.version} onValueChange={(v) => v && onVersionChange(v)}>
          <SelectTrigger className="w-24 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            {availableVersions.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <button onClick={onRemove} className="text-muted-foreground hover:text-destructive transition-colors shrink-0">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

// ── Addon Catalog Card ────────────────────────────────────────────────────────

function AddonCatalogCard({ addon, isSelected, onAdd }: {
  addon: AddonCatalogEntry; isSelected: boolean; onAdd: (version: string) => void;
}) {
  const [selectedVersion, setSelectedVersion] = useState(addon.current_version);
  return (
    <div
      data-testid={`addon-card-${addon.team}-${addon.name}`}
      className={cn("rounded-xl border bg-card p-4 transition-all",
        isSelected ? "border-primary/50 bg-primary/5 opacity-60" : "hover:shadow-md hover:border-primary/30")}
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
        {isSelected && <span className="rounded-full px-2 py-0.5 text-xs bg-primary/10 text-primary font-medium shrink-0">Added</span>}
      </div>
      <div className="flex items-center gap-2">
        <Select value={selectedVersion} onValueChange={(v) => v && setSelectedVersion(v)} disabled={isSelected}>
          <SelectTrigger className="flex-1 h-8 text-xs">
            <Tag className="h-3 w-3 mr-1" /><SelectValue />
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false}>
            {addon.available_versions.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <button onClick={() => onAdd(selectedVersion)} disabled={isSelected}
          className={cn(buttonVariants({ variant: "outline", size: "sm" }), "h-8 shrink-0", isSelected && "opacity-50 cursor-not-allowed")}>
          <Plus className="h-3.5 w-3.5 mr-1" />Add
        </button>
      </div>
    </div>
  );
}

// ── Team Section ──────────────────────────────────────────────────────────────

function TeamSection({ team, addons, selectedAddons, onAdd }: {
  team: string; addons: AddonCatalogEntry[]; selectedAddons: SpecAddon[];
  onAdd: (addon: AddonCatalogEntry, version: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const isAddonSelected = (a: AddonCatalogEntry) => selectedAddons.some((s) => s.team === a.team && s.name === a.name);
  return (
    <div className="space-y-3">
      <button onClick={() => setExpanded((v) => !v)} className="flex items-center gap-2 group w-full text-left">
        {expanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
        <span className="text-sm font-semibold group-hover:text-primary transition-colors">{team}</span>
        <span className="rounded-full px-2 py-0.5 text-xs bg-muted text-muted-foreground font-medium">{addons.length}</span>
      </button>
      {expanded && (
        <div className="grid gap-3 sm:grid-cols-2 pl-6">
          {addons.map((addon) => (
            <AddonCatalogCard key={`${addon.team}-${addon.name}`} addon={addon} isSelected={isAddonSelected(addon)}
              onAdd={(version) => onAdd(addon, version)} />
          ))}
        </div>
      )}
    </div>
  );
}

// (Legacy SpecVariable editor removed — cluster structure now defined via DynamicVariableForm)

const IDENTITY_VAR_NAMES = new Set([
  "cluster_name", "site", "site_name", "mce", "mce_name", "openshift_release_version",
]);

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function EditSpecPage() {
  const params = useParams();
  const specName = params.name as string;
  const router = useRouter();

  const [specVersion, setSpecVersion] = useState<string | null>(null);
  const [selectedAddons, setSelectedAddons] = useState<SpecAddon[] | null>(null);
  const [structure, setStructure] = useState<FormValues | null>(null);
  const [immutablePaths, setImmutablePaths] = useState<Set<string> | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [addonSearch, setAddonSearch] = useState("");
  const [configuringAddon, setConfiguringAddon] = useState<{ team: string; name: string } | null>(null);

  const { data: spec, isLoading: specLoading } = useQuery<ClusterSpec>({
    queryKey: ["specs", specName],
    queryFn: () => api.get<ClusterSpec>(`/api/day1/specs/${specName}`),
    staleTime: 60_000,
  });

  const { data: addonCatalog, isLoading: catalogLoading } = useQuery<AddonCatalogEntry[]>({
    queryKey: ["addons", "catalog"],
    queryFn: () => api.get<AddonCatalogEntry[]>("/api/day2/addons"),
    staleTime: 120_000,
  });

  const { data: templateSchema = [] } = useQuery<TemplateField[]>({
    queryKey: ["specs", "template-schema-all"],
    queryFn: () => api.get<TemplateField[]>("/api/day1/specs/template/schema?include_reserved=true"),
    staleTime: 300_000,
  });

  const effectiveVersion = specVersion ?? spec?.metadata.version ?? "1.0.0";
  const sharedTemplate = spec?.spec.day1.template ?? "";
  const effectiveAddons = selectedAddons ?? spec?.spec.day2.addons ?? [];
  // Seed structure from spec on first render; fall back to blank template defaults
  const effectiveStructure = structure ?? (spec?.spec.day1.structure
    ? spec.spec.day1.structure as FormValues
    : (templateSchema.length > 0 ? initFormValues(templateSchema) : {}));
  const effectiveImmutablePaths = immutablePaths ?? new Set<string>(spec?.spec.day1.immutable_paths ?? []);

  const handleToggleImmutable = (path: string) => {
    setImmutablePaths((prev) => {
      const base = prev ?? effectiveImmutablePaths;
      const next = new Set(base);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };

  const addonVersionsMap = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const addon of addonCatalog ?? []) map[`${addon.team}/${addon.name}`] = addon.available_versions;
    return map;
  }, [addonCatalog]);

  const filteredCatalog = useMemo(() => {
    if (!addonCatalog) return {};
    const filtered = addonCatalog.filter(
      (a) => addonSearch.trim() === "" ||
        a.name.toLowerCase().includes(addonSearch.toLowerCase()) ||
        a.team.toLowerCase().includes(addonSearch.toLowerCase())
    );
    return filtered.reduce<Record<string, AddonCatalogEntry[]>>((acc, addon) => {
      if (!acc[addon.team]) acc[addon.team] = [];
      acc[addon.team].push(addon);
      return acc;
    }, {});
  }, [addonCatalog, addonSearch]);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = effectiveAddons.findIndex((a) => `${a.team}/${a.name}` === active.id);
      const newIndex = effectiveAddons.findIndex((a) => `${a.team}/${a.name}` === over.id);
      setSelectedAddons(arrayMove(effectiveAddons, oldIndex, newIndex));
    }
  };

  const handleSaveOverrideable = (fields: OverrideableField[]) => {
    if (!configuringAddon) return;
    setSelectedAddons(effectiveAddons.map((a) =>
      a.team === configuringAddon.team && a.name === configuringAddon.name ? { ...a, overrideable: fields } : a
    ));
    setConfiguringAddon(null);
  };

  const configuringAddonData = configuringAddon
    ? effectiveAddons.find((a) => a.team === configuringAddon.team && a.name === configuringAddon.name)
    : null;
  const configuringCatalogEntry = configuringAddon
    ? addonCatalog?.find((c) => c.team === configuringAddon.team && c.name === configuringAddon.name)
    : null;

  const configuringVersion = configuringAddonData?.version ?? configuringCatalogEntry?.current_version;
  const { data: configuringChartValues, isLoading: configuringChartLoading } = useQuery<Record<string, unknown>>({
    queryKey: ["addons", configuringAddon?.team, configuringAddon?.name, "values", configuringVersion],
    queryFn: () => api.get<Record<string, unknown>>(
      `/api/day2/addons/${configuringAddon!.team}/${configuringAddon!.name}/values?version=${encodeURIComponent(configuringVersion!)}`
    ),
    enabled: Boolean(configuringAddon && configuringVersion),
    staleTime: 300_000,
  });

  const configuringDefaultValues = configuringChartValues
    ? { ...configuringChartValues, ...(configuringCatalogEntry?.default_values ?? {}) }
    : (configuringCatalogEntry?.default_values ?? {});

  const buildFinalSpec = (): ClusterSpec => {
    return {
      apiVersion: spec?.apiVersion ?? "wingman.io/v1",
      kind: spec?.kind ?? "ClusterSpec",
      metadata: { name: specName, version: effectiveVersion, labels: spec?.metadata.labels ?? {} },
      spec: {
        day1: {
          variables: [],
          structure: Object.fromEntries(
            Object.entries(effectiveStructure).filter(([k]) => !IDENTITY_VAR_NAMES.has(k))
          ) as Record<string, unknown>,
          immutable_paths: [...effectiveImmutablePaths],
          template: "",
        },
        day2: { addons: effectiveAddons },
      },
    };
  };

  const originalFullYaml = useMemo(() => {
    if (!spec) return "";
    return jsYaml.dump(spec, { lineWidth: 120, quotingType: '"' });
  }, [spec]);

  const currentFullYaml = useMemo(() => {
    try { return jsYaml.dump(buildFinalSpec(), { lineWidth: 120, quotingType: '"' }); }
    catch { return ""; }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specName, effectiveVersion, effectiveStructure, effectiveImmutablePaths, effectiveAddons]);

  const diff = useMemo(() => computeLineDiff(originalFullYaml, currentFullYaml), [originalFullYaml, currentFullYaml]);

  const updateMutation = useMutation({
    mutationFn: async () => api.put<MRDetail>(`/api/day1/specs/${specName}`, buildFinalSpec()),
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
    try { buildFinalSpec(); } catch (e) { toast.error((e as Error).message); return; }
    setReviewOpen(true);
  };

  const isLoading = specLoading || catalogLoading;

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href={`/specs/${specName}`} className={buttonVariants({ variant: "ghost", size: "icon" })}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Edit Spec
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Editing <span className="font-medium">{specName}</span>
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-6">
          <Skeleton className="h-20 rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
          <Skeleton className="h-96 rounded-xl" />
        </div>
      ) : (
        <>
          {/* Version */}
          <div className="bg-card rounded-xl border shadow-sm p-4">
            <div className="max-w-xs">
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Version</label>
              <input
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                value={effectiveVersion}
                onChange={(e) => setSpecVersion(e.target.value)}
              />
            </div>
          </div>

          {/* Shared Cluster Template — read-only reference */}
          <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b bg-muted/20">
              <FileCode2 className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-sm font-semibold">Cluster Template</span>
              <span className="ml-1 text-xs text-muted-foreground">— shared across all specs</span>
              <span className="ml-auto text-xs text-muted-foreground font-mono">cluster-template.j2</span>
            </div>
            <pre className="w-full font-mono text-xs bg-zinc-950 text-zinc-300/70 p-4 max-h-[300px] overflow-auto leading-5 select-text">
              {sharedTemplate || "Loading shared template…"}
            </pre>
          </div>

          {/* Cluster Structure */}
          <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b bg-muted/20">
              <Tag className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-sm font-semibold">Cluster Structure</span>
              <span className="ml-1 text-xs text-muted-foreground">— add list items to set counts; toggle 🔒 to lock fields post-create</span>
            </div>
            <div className="p-4">
              {templateSchema.length === 0 ? (
                <div className="rounded-lg border-2 border-dashed p-6 text-center text-sm text-muted-foreground">
                  Loading structure from template…
                </div>
              ) : (
                <div className="space-y-2">
                  <DynamicVariableForm
                    schema={templateSchema}
                    values={effectiveStructure}
                    onChange={(v) => setStructure(v)}
                    mode="spec-build"
                    immutablePaths={effectiveImmutablePaths}
                    onToggleImmutable={handleToggleImmutable}
                  />
                  {effectiveImmutablePaths.size > 0 && (
                    <div className="mt-3 pt-3 border-t">
                      <p className="text-xs text-muted-foreground font-medium mb-1">Immutable after create:</p>
                      <div className="flex flex-wrap gap-1.5">
                        {[...effectiveImmutablePaths].map((p) => (
                          <span key={p} className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs px-2 py-0.5 font-mono">
                            {p}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Day2 Addons */}
          <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b bg-muted/20">
              <span className="text-sm font-semibold">Day 2 — Addons</span>
              <p className="text-xs text-muted-foreground mt-0.5">Select addons and drag to set install order</p>
            </div>
            <div className="p-4 grid lg:grid-cols-2 gap-6">
              {/* Left: Available */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Available Addons</h3>
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                    <input type="text" placeholder="Search..." value={addonSearch}
                      onChange={(e) => setAddonSearch(e.target.value)}
                      className="w-40 rounded-lg border bg-background pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50" />
                  </div>
                </div>
                <div className="max-h-[500px] overflow-y-auto space-y-6 pr-2">
                  {Object.keys(filteredCatalog).length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-8">
                      {addonSearch ? "No addons match your search" : "No addons available"}
                    </p>
                  ) : (
                    Object.entries(filteredCatalog).sort(([a], [b]) => a.localeCompare(b))
                      .map(([team, addons]) => (
                        <TeamSection key={team} team={team} addons={addons} selectedAddons={effectiveAddons}
                          onAdd={(addon, version) => setSelectedAddons([...effectiveAddons, { team: addon.team, name: addon.name, version, overrideable: [] }])} />
                      ))
                  )}
                </div>
              </div>

              {/* Right: Selected */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Selected Addons ({effectiveAddons.length})</h3>
                  <span className="text-xs text-muted-foreground">Drag to reorder</span>
                </div>
                {effectiveAddons.length === 0 ? (
                  <div className="rounded-xl border-2 border-dashed p-8 text-center">
                    <Package className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">No addons selected</p>
                    <p className="text-xs text-muted-foreground mt-1">Click &ldquo;Add&rdquo; on an addon to include it</p>
                  </div>
                ) : (
                  <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                    <SortableContext items={effectiveAddons.map((a) => `${a.team}/${a.name}`)} strategy={verticalListSortingStrategy}>
                      <div className="space-y-2">
                        {effectiveAddons.map((addon, index) => (
                          <SortableAddonItem
                            key={`${addon.team}/${addon.name}`}
                            addon={addon}
                            index={index}
                            onRemove={() => setSelectedAddons(effectiveAddons.filter((a) => !(a.team === addon.team && a.name === addon.name)))}
                            onVersionChange={(v) => setSelectedAddons(effectiveAddons.map((a) => a.team === addon.team && a.name === addon.name ? { ...a, version: v } : a))}
                            onConfigure={() => setConfiguringAddon({ team: addon.team, name: addon.name })}
                            availableVersions={addonVersionsMap[`${addon.team}/${addon.name}`] ?? [addon.version]}
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
            <Link href={`/specs/${specName}`} className={buttonVariants({ variant: "outline" })}>Cancel</Link>
            <button onClick={handleReview}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors">
              <Eye className="h-4 w-4" />Review & Update
            </button>
          </div>
        </>
      )}

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title={`Review: Update Spec "${specName}"`}
        description={diff ? "Changed lines are highlighted below." : "No changes detected."}
        diff={diff || undefined}
        onConfirm={() => updateMutation.mutate()}
        isPending={updateMutation.isPending}
        confirmLabel="Confirm — Update Spec MR"
      >
        {!diff && <p className="text-sm text-muted-foreground italic text-center py-4">Nothing changed.</p>}
      </ReviewDialog>

      {configuringAddon && (
        <ConfigureOverrideableDialog
          key={`${configuringAddon.team}/${configuringAddon.name}`}
          open={true}
          onOpenChange={(open) => !open && setConfiguringAddon(null)}
          addonName={configuringAddon.name}
          defaultValues={configuringDefaultValues}
          isLoadingValues={configuringChartLoading}
          currentOverrideable={configuringAddonData?.overrideable ?? []}
          onSave={handleSaveOverrideable}
        />
      )}
    </div>
  );
}
