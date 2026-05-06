"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
import { asNewFile } from "@/lib/diff";
import { useIsAdmin } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ConfigureOverrideableDialog } from "@/components/specs/configure-overrideable-dialog";
import type { MRDetail, AddonCatalogEntry, SpecAddon, ClusterSpec, OverrideableField } from "@/types";

const DAY1_TEMPLATE = `apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: my-spec
  description: "Describe your cluster spec"
  version: "1.0.0"
  labels:
    tier: production
spec:
  day1:
    variables:
      - name: cluster_name
        type: string
        required: true
        description: "Name of the cluster"
      - name: ocp_version
        type: string
        required: true
        enum:
          - "4.14.12"
          - "4.15.3"
          - "4.16.0"
    template: |
      ---
      apiVersion: hypershift.openshift.io/v1beta1
      kind: HostedCluster
      metadata:
        name: {{ cluster_name }}
      spec:
        release:
          image: registry.internal/ocp-release:{{ ocp_version }}
`;

// ── Sortable Addon Item ───────────────────────────────────────────────────────

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

  const overrideCount = addon.overrideable?.length ?? 0;

  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`selected-addon-${addon.team}-${addon.name}`}
      className={cn(
        "flex items-center gap-3 rounded-lg border bg-card p-3 transition-shadow",
        isDragging && "shadow-lg ring-2 ring-primary/50 z-10"
      )}
    >
      <button
        {...attributes}
        {...listeners}
        data-testid="drag-handle"
        className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground touch-none shrink-0"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary shrink-0">
        {index + 1}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{addon.name}</p>
        <p className="text-xs text-muted-foreground truncate">
          {addon.team}
          {overrideCount > 0 && (
            <span className="ml-2 text-primary">
              · {overrideCount} overrideable
            </span>
          )}
        </p>
      </div>
      <button
        onClick={onConfigure}
        className={cn(
          buttonVariants({ variant: "ghost", size: "sm" }),
          "h-8 px-2 shrink-0"
        )}
        title="Configure overrideable fields"
      >
        <Settings2 className="h-4 w-4" />
      </button>
      <div className="shrink-0">
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
      </div>
      <button
        onClick={onRemove}
        className="text-muted-foreground hover:text-destructive transition-colors shrink-0"
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
      data-testid={`addon-card-${addon.team}-${addon.name}`}
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

export default function NewSpecPage() {
  const isAdmin = useIsAdmin();
  const router = useRouter();

  // Day1 YAML state
  const [day1Yaml, setDay1Yaml] = useState(DAY1_TEMPLATE);

  // Day2 addons state
  const [selectedAddons, setSelectedAddons] = useState<SpecAddon[]>([]);

  // UI state
  const [reviewOpen, setReviewOpen] = useState(false);
  const [addonSearch, setAddonSearch] = useState("");
  const [configuringAddon, setConfiguringAddon] = useState<{
    team: string;
    name: string;
  } | null>(null);

  // Fetch addon catalog
  const { data: addonCatalog, isLoading: catalogLoading } = useQuery<
    AddonCatalogEntry[]
  >({
    queryKey: ["addons", "catalog"],
    queryFn: () => api.get<AddonCatalogEntry[]>("/api/day2/addons"),
    staleTime: 120_000,
  });

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
      const oldIndex = selectedAddons.findIndex(
        (a) => `${a.team}/${a.name}` === active.id
      );
      const newIndex = selectedAddons.findIndex(
        (a) => `${a.team}/${a.name}` === over.id
      );
      setSelectedAddons(arrayMove(selectedAddons, oldIndex, newIndex));
    }
  };

  // Add addon
  const handleAddAddon = (addon: AddonCatalogEntry, version: string) => {
    const newAddon: SpecAddon = {
      team: addon.team,
      name: addon.name,
      version,
      overrideable: [],
    };
    setSelectedAddons([...selectedAddons, newAddon]);
  };

  // Remove addon
  const handleRemoveAddon = (team: string, name: string) => {
    setSelectedAddons(selectedAddons.filter((a) => !(a.team === team && a.name === name)));
  };

  // Change addon version
  const handleVersionChange = (team: string, name: string, version: string) => {
    setSelectedAddons(
      selectedAddons.map((a) =>
        a.team === team && a.name === name ? { ...a, version } : a
      )
    );
  };

  // Configure addon overrideable fields
  const handleConfigureAddon = (team: string, name: string) => {
    setConfiguringAddon({ team, name });
  };

  // Save overrideable fields for an addon
  const handleSaveOverrideable = (fields: OverrideableField[]) => {
    if (!configuringAddon) return;
    setSelectedAddons(
      selectedAddons.map((a) =>
        a.team === configuringAddon.team && a.name === configuringAddon.name
          ? { ...a, overrideable: fields }
          : a
      )
    );
    setConfiguringAddon(null);
  };

  // Get the addon being configured and its catalog entry
  const configuringAddonData = configuringAddon
    ? selectedAddons.find(
        (a) => a.team === configuringAddon.team && a.name === configuringAddon.name
      )
    : null;
  const configuringCatalogEntry = configuringAddon
    ? addonCatalog?.find(
        (c) => c.team === configuringAddon.team && c.name === configuringAddon.name
      )
    : null;

  // Build final spec for save
  const buildFinalSpec = (): ClusterSpec => {
    let day1Parsed: unknown;
    try {
      day1Parsed = jsYaml.load(day1Yaml);
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
          addons: selectedAddons,
        },
      },
    };
  };

  // Build YAML for review
  const finalYaml = useMemo(() => {
    try {
      return jsYaml.dump(buildFinalSpec(), { lineWidth: 120, quotingType: '"' });
    } catch {
      return "";
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day1Yaml, selectedAddons]);

  // Save mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      const finalSpec = buildFinalSpec();
      return api.post<MRDetail>("/api/day1/specs", finalSpec);
    },
    onSuccess: (mr) => {
      toast.success(`Spec MR #${mr.iid} created: ${mr.title}`);
      setReviewOpen(false);
      router.push("/specs");
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

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3 text-center">
        <p className="text-lg font-semibold">Insufficient permissions</p>
        <p className="text-sm text-muted-foreground">Your role (viewer) does not have access to create specs.</p>
        <Link href="/specs" className={buttonVariants({ variant: "outline", size: "sm" })}>Back to specs</Link>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          href="/specs"
          className={buttonVariants({ variant: "ghost", size: "icon" })}
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            New Spec
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Define a cluster template
          </p>
        </div>
      </div>

      {/* Day1 Section */}
      <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/20">
          <span className="text-sm font-semibold">Day 1 — Cluster Template</span>
          <span className="text-xs text-muted-foreground">
            Metadata, variables, and template
          </span>
        </div>
        <textarea
          className="w-full font-mono text-xs bg-zinc-950 text-zinc-200 p-4 min-h-[300px] focus:outline-none resize-y leading-5"
          value={day1Yaml}
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

        {catalogLoading ? (
          <div className="p-4">
            <Skeleton className="h-64" />
          </div>
        ) : (
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
                        selectedAddons={selectedAddons}
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
                  Selected Addons ({selectedAddons.length})
                </h3>
                <span className="text-xs text-muted-foreground">
                  Drag to reorder
                </span>
              </div>

              {selectedAddons.length === 0 ? (
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
                    items={selectedAddons.map((a) => `${a.team}/${a.name}`)}
                    strategy={verticalListSortingStrategy}
                  >
                    <div className="space-y-2">
                      {selectedAddons.map((addon, index) => (
                        <SortableAddonItem
                          key={`${addon.team}/${addon.name}`}
                          addon={addon}
                          index={index}
                          onRemove={() => handleRemoveAddon(addon.team, addon.name)}
                          onVersionChange={(v) =>
                            handleVersionChange(addon.team, addon.name, v)
                          }
                          onConfigure={() =>
                            handleConfigureAddon(addon.team, addon.name)
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
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <Link href="/specs" className={buttonVariants({ variant: "outline" })}>
          Cancel
        </Link>
        <button
          onClick={handleReview}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
        >
          <Eye className="h-4 w-4" />
          Review & Create
        </button>
      </div>

      {/* Review Dialog */}
      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title="Review: Create Spec"
        description="The spec below will be created as a new file in GitLab and submitted as an MR for approval."
        diff={asNewFile(finalYaml)}
        onConfirm={() => createMutation.mutate()}
        isPending={createMutation.isPending}
        confirmLabel="Confirm — Create Spec MR"
      />

      {/* Configure Overrideable Fields Dialog */}
      {configuringAddon && (
        <ConfigureOverrideableDialog
          key={`${configuringAddon.team}/${configuringAddon.name}`}
          open={true}
          onOpenChange={(open) => !open && setConfiguringAddon(null)}
          addonName={configuringAddon.name}
          defaultValues={configuringCatalogEntry?.default_values ?? {}}
          currentOverrideable={configuringAddonData?.overrideable ?? []}
          onSave={handleSaveOverrideable}
        />
      )}
    </div>
  );
}
