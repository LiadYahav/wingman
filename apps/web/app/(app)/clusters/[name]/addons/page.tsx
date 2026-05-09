"use client";

import { useState, useMemo, Suspense, useCallback, useRef, useEffect } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Package, Plus, Trash2, ChevronDown, ChevronUp, Eye, Users, AlignJustify, Code2, RefreshCw, X, CheckCircle2, Loader2, MoreVertical, AlertTriangle, GripVertical, Copy, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api-client";
import { useIsAdmin } from "@/stores/auth-store";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import jsYaml from "js-yaml";
import { ReviewDialog as SharedReviewDialog } from "@/components/common/review-dialog";
import { computeLineDiff } from "@/lib/diff";
import type { AddonCatalogEntry, InstalledAddon, MergedAddonValues, MRDetail, ClusterStatus } from "@/types";

// ── Value helpers ──────────────────────────────────────────────────────────────

function isComplexValue(v: unknown): boolean {
  if (Array.isArray(v)) {
    // Arrays of primitives are simple, arrays with objects/arrays are complex
    return v.some(item => typeof item === "object" && item !== null);
  }
  return false;
}

function flattenValues(obj: Record<string, unknown>, prefix = ""): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object" && !Array.isArray(v)) {
      Object.assign(out, flattenValues(v as Record<string, unknown>, key));
    } else {
      // Keep arrays (including complex ones) as-is - they'll be rendered specially
      out[key] = v;
    }
  }
  return out;
}

function unflattenValues(flat: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(flat)) {
    const parts = key.split(".");
    let cursor = out;
    for (let i = 0; i < parts.length - 1; i++) {
      if (typeof cursor[parts[i]] !== "object" || cursor[parts[i]] === null) {
        cursor[parts[i]] = {};
      }
      cursor = cursor[parts[i]] as Record<string, unknown>;
    }
    // Preserve complex values (arrays/objects) as-is, only coerce simple values
    if (typeof value === "object" && value !== null) {
      cursor[parts[parts.length - 1]] = value;
    } else {
      cursor[parts[parts.length - 1]] = coerce(String(value ?? ""));
    }
  }
  return out;
}

function coerce(s: string): unknown {
  if (s === "true") return true;
  if (s === "false") return false;
  if (s === "null") return null;
  if (s.trim() === "") return "";
  const n = Number(s);
  return Number.isFinite(n) ? n : s;
}

function getProvenance(provenance: Record<string, unknown>, key: string): string {
  const parts = key.split(".");
  let cursor: unknown = provenance;
  for (const part of parts) {
    if (typeof cursor !== "object" || cursor === null) return "";
    cursor = (cursor as Record<string, unknown>)[part];
  }
  return typeof cursor === "string" ? cursor : "";
}

const ReviewDialog = SharedReviewDialog;

// ── Array Editor ───────────────────────────────────────────────────────────────
// Interactive editor for arrays of objects (e.g., network segments, IP pools)

function ArrayItemEditor({
  item,
  index,
  onUpdate,
  onRemove,
  onClone,
  isExpanded,
  onToggle,
}: {
  item: Record<string, unknown>;
  index: number;
  onUpdate: (newItem: Record<string, unknown>) => void;
  onRemove: () => void;
  onClone: () => void;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  // Get a summary of the item for the collapsed view
  const summary = Object.entries(item)
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${typeof v === "object" ? "..." : v}`)
    .join(", ");

  return (
    <div className="border rounded-lg bg-card overflow-hidden">
      {/* Header - always visible */}
      <div
        className="flex items-center gap-2 px-3 py-2 bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={onToggle}
      >
        <GripVertical className="h-4 w-4 text-muted-foreground/50" />
        <span className="text-xs font-medium text-primary">#{index + 1}</span>
        <span className="text-xs text-muted-foreground truncate flex-1">{summary}</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onClone(); }}
            className="p-1 hover:bg-muted rounded transition-colors"
            title="Clone item"
          >
            <Copy className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onRemove(); }}
            className="p-1 hover:bg-destructive/10 rounded transition-colors"
            title="Remove item"
          >
            <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
          </button>
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="p-3 space-y-2 border-t">
          {Object.entries(item).map(([key, value]) => (
            <div key={key} className="grid grid-cols-[35%_65%] gap-2 items-center">
              <label className="text-xs font-mono text-muted-foreground truncate" title={key}>
                {key}
              </label>
              {typeof value === "object" && value !== null ? (
                <textarea
                  className="w-full bg-muted/30 font-mono text-xs rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary/50 resize-y min-h-[40px]"
                  value={jsYaml.dump(value, { flowLevel: -1 }).trim()}
                  onChange={(e) => {
                    try {
                      const parsed = jsYaml.load(e.target.value);
                      onUpdate({ ...item, [key]: parsed });
                    } catch {
                      // Invalid YAML, keep as string for now
                    }
                  }}
                />
              ) : (
                <input
                  type="text"
                  className="w-full bg-muted/30 font-mono text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary/50"
                  value={String(value ?? "")}
                  onChange={(e) => onUpdate({ ...item, [key]: coerce(e.target.value) })}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ArrayEditor({
  value,
  onChange,
}: {
  value: unknown[];
  onChange: (newValue: unknown[]) => void;
}) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(0);

  // Get template for new items from first item or create empty object
  const getNewItemTemplate = (): Record<string, unknown> => {
    if (value.length > 0 && typeof value[0] === "object" && value[0] !== null) {
      const template: Record<string, unknown> = {};
      for (const key of Object.keys(value[0] as Record<string, unknown>)) {
        template[key] = "";
      }
      return template;
    }
    return { key: "", value: "" };
  };

  const handleAdd = () => {
    const newItem = getNewItemTemplate();
    const newValue = [...value, newItem];
    onChange(newValue);
    setExpandedIndex(newValue.length - 1);
  };

  const handleUpdate = (index: number, newItem: Record<string, unknown>) => {
    const newValue = [...value];
    newValue[index] = newItem;
    onChange(newValue);
  };

  const handleRemove = (index: number) => {
    const newValue = value.filter((_, i) => i !== index);
    onChange(newValue);
    if (expandedIndex === index) {
      setExpandedIndex(null);
    } else if (expandedIndex !== null && expandedIndex > index) {
      setExpandedIndex(expandedIndex - 1);
    }
  };

  const handleClone = (index: number) => {
    const cloned = JSON.parse(JSON.stringify(value[index]));
    const newValue = [...value];
    newValue.splice(index + 1, 0, cloned);
    onChange(newValue);
    setExpandedIndex(index + 1);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {value.length} item{value.length !== 1 ? "s" : ""}
        </span>
        <button
          type="button"
          onClick={handleAdd}
          className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          Add item
        </button>
      </div>
      <div className="space-y-2">
        {value.map((item, index) => (
          <ArrayItemEditor
            key={index}
            item={item as Record<string, unknown>}
            index={index}
            onUpdate={(newItem) => handleUpdate(index, newItem)}
            onRemove={() => handleRemove(index)}
            onClone={() => handleClone(index)}
            isExpanded={expandedIndex === index}
            onToggle={() => setExpandedIndex(expandedIndex === index ? null : index)}
          />
        ))}
      </div>
      {value.length === 0 && (
        <p className="text-xs text-muted-foreground italic text-center py-4">
          No items. Click &quot;Add item&quot; to create one.
        </p>
      )}
    </div>
  );
}

// ── Values table ───────────────────────────────────────────────────────────────
// Shared between installed (editable) and available (editable) addon cards.

function formatValueForDisplay(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") {
    // Format arrays/objects as YAML for display
    return jsYaml.dump(v, { flowLevel: -1, lineWidth: -1 }).trim();
  }
  return String(v);
}

function parseValueFromInput(s: string, originalValue: unknown): unknown {
  // If original was complex (array/object), try to parse as YAML
  if (typeof originalValue === "object" && originalValue !== null) {
    try {
      return jsYaml.load(s);
    } catch {
      // If YAML parse fails, return as string
      return s;
    }
  }
  // For simple values, use the coerce function
  return coerce(s);
}

function ValuesTable({
  entries,
  provenance,
  onChange,
  onComplexChange,
}: {
  entries: [string, unknown][];
  provenance?: Record<string, unknown>;
  onChange: (key: string, value: string) => void;
  onComplexChange?: (key: string, value: unknown) => void;
}) {
  if (entries.length === 0) {
    return (
      <p className="text-xs text-muted-foreground italic px-1">No configurable values</p>
    );
  }

  return (
    <div className="rounded-lg border overflow-hidden text-xs">
      {/* Header */}
      <div className="grid grid-cols-[40%_60%] bg-muted/40 border-b">
        <div className="px-3 py-1.5 font-semibold text-muted-foreground uppercase tracking-wide text-[10px]">Key</div>
        <div className="px-3 py-1.5 font-semibold text-muted-foreground uppercase tracking-wide text-[10px] border-l">Value</div>
      </div>

      {/* Rows */}
      {entries.map(([k, v]) => {
        const prov = provenance ? getProvenance(provenance, k) : "";
        const borderColor =
          prov === "cluster" ? "border-l-[#0073ea]" :
          prov === "team"    ? "border-l-[#00c875]" :
          "border-l-transparent";

        const isComplex = isComplexValue(v);
        const isArrayOfObjects = Array.isArray(v) && v.length > 0 && typeof v[0] === "object";
        const displayValue = formatValueForDisplay(v);

        // For arrays of objects, render full-width with interactive editor
        if (isArrayOfObjects && onComplexChange) {
          return (
            <div
              key={k}
              className={cn("border-b last:border-b-0 border-l-2", borderColor)}
            >
              <div className="flex items-center justify-between px-3 py-2 bg-muted/20 border-b">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-muted-foreground" title={k}>{k}</span>
                  <span className="text-[9px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-medium">
                    Array
                  </span>
                </div>
              </div>
              <div className="p-3">
                <ArrayEditor
                  value={v as unknown[]}
                  onChange={(newValue) => onComplexChange(k, newValue)}
                />
              </div>
            </div>
          );
        }

        return (
          <div
            key={k}
            className={cn(
              "grid grid-cols-[40%_60%] border-b last:border-b-0 border-l-2 hover:bg-muted/20 transition-colors",
              borderColor
            )}
          >
            <div className={cn("flex px-3 py-2 border-r overflow-hidden", isComplex ? "items-start pt-3" : "items-center")}>
              <span
                className="font-mono text-muted-foreground truncate leading-4"
                title={k}
              >
                {k}
              </span>
              {isComplex && (
                <span className="ml-1.5 text-[9px] bg-amber-500/20 text-amber-600 dark:text-amber-400 px-1 py-0.5 rounded font-medium">
                  YAML
                </span>
              )}
            </div>
            <div className="flex items-center px-2 py-1">
              {isComplex ? (
                <textarea
                  className="w-full bg-muted/30 font-mono focus:outline-none focus:bg-primary/5 rounded px-2 py-1.5 transition-colors resize-y min-h-[60px] text-[11px] leading-relaxed"
                  value={displayValue}
                  rows={Math.min(8, displayValue.split("\n").length + 1)}
                  onChange={(e) => {
                    if (onComplexChange) {
                      const parsed = parseValueFromInput(e.target.value, v);
                      onComplexChange(k, parsed);
                    }
                  }}
                />
              ) : (
                <input
                  type="text"
                  className="w-full bg-transparent font-mono focus:outline-none focus:bg-primary/5 rounded px-1 py-0.5 transition-colors"
                  value={displayValue}
                  onChange={(e) => onChange(k, e.target.value)}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Provenance legend ──────────────────────────────────────────────────────────

function ProvenanceLegend() {
  return (
    <div className="flex items-center gap-4 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#0073ea]" />
        cluster override
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#00c875]" />
        team default
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-2.5 h-2.5 rounded-sm border border-border" />
        chart default
      </span>
    </div>
  );
}

// ── View mode toggle ──────────────────────────────────────────────────────────

type ViewMode = "form" | "yaml";

function ViewToggle({ mode, onChange }: { mode: ViewMode; onChange: (m: ViewMode) => void }) {
  return (
    <div className="inline-flex rounded-lg border bg-muted/40 p-0.5 gap-0.5">
      <button
        onClick={() => onChange("form")}
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors",
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
          "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors",
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

// ── Installed addon card ───────────────────────────────────────────────────────

interface ClusterInstalledResponse {
  cluster: string;
  mce: string;
  installed: InstalledAddon[];
}

function InstalledAddonCard({
  addon, clusterName, mce, isAdmin,
}: {
  addon: InstalledAddon; clusterName: string; mce: string; isAdmin: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("form");
  const [editValues, setEditValues] = useState<Record<string, unknown>>(
    () => flattenValues(addon.override_values)
  );
  const [selectedVersion, setSelectedVersion] = useState(addon.version || "main");
  const [yamlText, setYamlText] = useState("");
  const [yamlError, setYamlError] = useState("");
  const [mergedLoaded, setMergedLoaded] = useState(false);
  const [updateReviewOpen, setUpdateReviewOpen] = useState(false);
  const [removeReviewOpen, setRemoveReviewOpen] = useState(false);
  const [removeConfirmText, setRemoveConfirmText] = useState("");

  function handleViewModeChange(next: ViewMode) {
    if (next === "yaml") {
      setYamlText(jsYaml.dump(unflattenValues(editValues), { indent: 2, lineWidth: -1 }));
      setYamlError("");
    } else {
      try {
        const parsed = (jsYaml.load(yamlText) as Record<string, unknown>) ?? {};
        setEditValues(flattenValues(parsed));
        setYamlError("");
      } catch {
        setYamlError("Invalid YAML — fix errors before switching to form view");
        return;
      }
    }
    setViewMode(next);
  }

  function handleYamlChange(text: string) {
    setYamlText(text);
    try {
      const parsed = (jsYaml.load(text) as Record<string, unknown>) ?? {};
      setEditValues(flattenValues(parsed));
      setYamlError("");
    } catch {
      setYamlError("Invalid YAML");
    }
  }
  const queryClient = useQueryClient();

  const { data: merged, isLoading: mergedLoading } = useQuery<MergedAddonValues>({
    queryKey: ["clusters", clusterName, "addons", addon.team, addon.name, "merged"],
    queryFn: () =>
      api.get<MergedAddonValues>(
        `/api/day2/clusters/${clusterName}/addons/${addon.team}/${addon.name}?mce=${mce}`
      ),
    enabled: expanded,
    staleTime: 60_000,
  });

  if (merged && !mergedLoaded) {
    setEditValues(flattenValues(merged.merged));
    setMergedLoaded(true);
  }

  const clusterOverrides = useMemo(() => {
    if (!merged) return unflattenValues(editValues);
    const existing = flattenValues(merged.cluster_values ?? {});
    const base = {
      ...flattenValues(merged.chart_values ?? {}),
      ...flattenValues(merged.team_values ?? {}),
    };
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(editValues)) {
      if (key in existing) {
        result[key] = value;
      } else if (String(value) !== String(base[key] ?? "")) {
        result[key] = value;
      }
    }
    return unflattenValues(result);
  }, [editValues, merged]);

  const versionChanged = selectedVersion !== (addon.version || "main");

  const hasChanges = useMemo(() => {
    if (versionChanged) return true;
    if (!merged) return true;
    return (
      jsYaml.dump(merged.cluster_values ?? {}, { sortKeys: true }) !==
      jsYaml.dump(clusterOverrides, { sortKeys: true })
    );
  }, [merged, clusterOverrides, versionChanged]);

  const updateMutation = useMutation({
    mutationFn: () =>
      api.put<MRDetail>(
        `/api/day2/clusters/${clusterName}/addons/${addon.team}/${addon.name}?mce=${mce}`,
        { version: selectedVersion, override_values: clusterOverrides }
      ),
    onSuccess: (mr) => {
      toast.success(`Update MR #${mr.iid} created: ${mr.title}`);
      setUpdateReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: ["clusters", clusterName, "addons"] });
    },
    onError: () => toast.error("Failed to create update MR"),
  });

  const removeMutation = useMutation({
    mutationFn: () =>
      api.del<MRDetail>(
        `/api/day2/clusters/${clusterName}/addons/${addon.team}/${addon.name}?mce=${mce}`
      ),
    onSuccess: (mr) => {
      toast.success(`Remove MR #${mr.iid} created: ${mr.title}`);
      setRemoveReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: ["clusters", clusterName, "addons"] });
    },
    onError: () => toast.error("Failed to create remove MR"),
  });

  return (
    <>
      <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
        {/* Header — always visible */}
        <div className="flex items-center justify-between px-4 py-3.5 hover:bg-muted/30 transition-colors">
          <button
            className="flex items-center gap-3 min-w-0 flex-1 text-left"
            onClick={() => setExpanded((v) => !v)}
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#00c875]/10 dark:bg-[#00c875]/20 shrink-0">
              <Package className="h-4 w-4 text-[#00c875]" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold truncate">{addon.name}</p>
              <p className="text-xs text-muted-foreground">{addon.team}</p>
            </div>
          </button>
          <div className="flex items-center gap-2 ml-3 shrink-0">
            <span className="rounded-full px-2 py-0.5 text-xs font-mono font-medium bg-primary/8 text-primary">
              {addon.version || "main"}
            </span>
            {addon.parse_errors && addon.parse_errors.length > 0 ? (
              <span className="rounded-full px-2 py-0.5 text-xs font-medium bg-destructive/10 text-destructive flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                YAML Error
              </span>
            ) : (
              <span className="rounded-full px-2 py-0.5 text-xs font-medium bg-[#00c875]/10 text-[#007038] dark:text-[#00c875]">
                Installed
              </span>
            )}
            <button onClick={() => setExpanded((v) => !v)} className="p-1 hover:bg-muted rounded transition-colors">
              {expanded
                ? <ChevronUp className="h-4 w-4 text-muted-foreground" />
                : <ChevronDown className="h-4 w-4 text-muted-foreground" />
              }
            </button>
            {/* 3-dot menu for quick actions */}
            {(isAdmin || addon.gitlab_url) && (
              <Popover>
                <PopoverTrigger
                  className="p-1 hover:bg-muted rounded transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  <MoreVertical className="h-4 w-4 text-muted-foreground" />
                </PopoverTrigger>
                <PopoverContent align="end" className="w-44 p-1">
                  {addon.gitlab_url && (
                    <a
                      href={addon.gitlab_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted rounded-md transition-colors"
                    >
                      <ExternalLink className="h-4 w-4" />
                      Open in GitLab
                    </a>
                  )}
                  {isAdmin && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setRemoveReviewOpen(true);
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove Addon
                    </button>
                  )}
                </PopoverContent>
              </Popover>
            )}
          </div>
        </div>

        {/* Expanded body */}
        {expanded && (
          <div className="border-t bg-muted/10 p-4 space-y-4">
            {/* Parse errors warning */}
            {addon.parse_errors && addon.parse_errors.length > 0 && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 space-y-3">
                <div className="flex items-center gap-2 text-destructive">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span className="text-sm font-semibold">YAML Configuration Error</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  This addon has invalid YAML configuration. Fix the errors in GitLab before updating.
                </p>
                {addon.parse_errors.map((err, i) => (
                  <div key={i} className="space-y-1.5">
                    <p className="text-xs text-destructive font-medium">
                      {err.line ? `Line ${err.line}${err.column ? `, Column ${err.column}` : ""}: ` : ""}
                      {err.message}
                    </p>
                    {err.snippet && (
                      <pre className="rounded bg-muted/50 p-2 text-[10px] font-mono overflow-x-auto whitespace-pre leading-relaxed">
                        {err.snippet}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Version selector */}
            {isAdmin && addon.available_versions && addon.available_versions.length > 0 && (
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Version</label>
                <select
                  className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                  value={selectedVersion}
                  onChange={(e) => setSelectedVersion(e.target.value)}
                >
                  {addon.available_versions.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
                {versionChanged && (
                  <p className="text-xs text-primary">Version will be updated from {addon.version || "main"} → {selectedVersion}</p>
                )}
              </div>
            )}

            {mergedLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : merged ? (
              <>
                <div className="flex items-center justify-between">
                  <ProvenanceLegend />
                  <ViewToggle mode={viewMode} onChange={handleViewModeChange} />
                </div>
                {viewMode === "form" ? (
                  <ValuesTable
                    entries={Object.entries(editValues)}
                    provenance={merged.provenance as Record<string, unknown>}
                    onChange={(k, val) => setEditValues((prev) => ({ ...prev, [k]: val }))}
                    onComplexChange={(k, val) => setEditValues((prev) => ({ ...prev, [k]: val }))}
                  />
                ) : (
                  <div className="space-y-1">
                    <textarea
                      className={cn(
                        "w-full rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow",
                        yamlError && "border-destructive/50"
                      )}
                      rows={Math.max(8, yamlText.split("\n").length + 1)}
                      value={yamlText}
                      onChange={(e) => handleYamlChange(e.target.value)}
                      spellCheck={false}
                    />
                    {yamlError && (
                      <p className="text-xs text-destructive">{yamlError}</p>
                    )}
                  </div>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground italic">No values available</p>
            )}

            {isAdmin && (
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => setUpdateReviewOpen(true)}
                  disabled={mergedLoading || !hasChanges || Boolean(yamlError) || (addon.parse_errors && addon.parse_errors.length > 0)}
                  title={
                    addon.parse_errors && addon.parse_errors.length > 0
                      ? "Fix YAML errors in GitLab first"
                      : !hasChanges
                        ? "No changes to submit"
                        : yamlError
                          ? "Fix YAML errors first"
                          : undefined
                  }
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Eye className="h-3.5 w-3.5" />
                  {hasChanges ? "Review & Update" : "No Changes"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Update review */}
      <ReviewDialog
        open={updateReviewOpen}
        onOpenChange={setUpdateReviewOpen}
        title={`Review: Update ${addon.name}`}
        description="Review the changes below. Confirming creates a GitLab MR for approval."
        onConfirm={() => updateMutation.mutate()}
        isPending={updateMutation.isPending}
      >
        <div className="space-y-4">
          {/* Summary */}
          <div className="text-sm space-y-1">
            <div className="flex gap-3">
              <span className="text-muted-foreground w-20 shrink-0">Addon</span>
              <span className="font-semibold">{addon.name}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-20 shrink-0">Version</span>
              <span className="font-medium">
                {versionChanged ? (
                  <><span className="line-through text-muted-foreground">{addon.version || "main"}</span> → <span className="text-primary">{selectedVersion}</span></>
                ) : (
                  addon.version || "main"
                )}
              </span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-20 shrink-0">Team</span>
              <span className="font-medium">{addon.team}</span>
            </div>
          </div>

          {/* File changes */}
          <div className="space-y-3">
            {/* {addon}.yaml - metadata file */}
            {versionChanged && (
              <div className="space-y-1">
                <p className="text-xs font-semibold text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-primary/10 text-primary mr-1.5">MODIFIED</span>
                  <code className="text-foreground font-mono text-[11px]">mces/{mce}/{clusterName}/{addon.name}/{addon.name}.yaml</code>
                </p>
                <pre className="rounded-lg bg-muted/50 border p-3 text-xs font-mono overflow-x-auto whitespace-pre">
                  <div className="text-destructive">- targetRevision: {addon.version || "main"}</div>
                  <div className="text-status-ready">+ targetRevision: {selectedVersion}</div>
                </pre>
              </div>
            )}

            {/* values.yaml */}
            <div className="space-y-1">
              <p className="text-xs font-semibold text-muted-foreground">
                <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-primary/10 text-primary mr-1.5">MODIFIED</span>
                <code className="text-foreground font-mono text-[11px]">mces/{mce}/{clusterName}/{addon.name}/values.yaml</code>
              </p>
              {(() => {
                const diff = computeLineDiff(
                  jsYaml.dump(merged?.cluster_values ?? {}, { sortKeys: true }),
                  jsYaml.dump(clusterOverrides, { sortKeys: true })
                );
                if (!diff || diff.trim().length === 0) {
                  return (
                    <div className="rounded-lg bg-muted/30 border border-dashed p-3 text-xs text-muted-foreground italic text-center">
                      No changes to values
                    </div>
                  );
                }
                const lines = diff.split("\n").filter(Boolean);
                return (
                  <pre className="rounded-lg bg-muted/50 border p-3 text-xs font-mono overflow-x-auto whitespace-pre max-h-48 overflow-y-auto">
                    {lines.map((line, i) => (
                      <div
                        key={i}
                        className={
                          line.startsWith("+") ? "text-status-ready" :
                          line.startsWith("-") ? "text-destructive" :
                          "text-muted-foreground"
                        }
                      >
                        {line}
                      </div>
                    ))}
                  </pre>
                );
              })()}
            </div>
          </div>
        </div>
      </ReviewDialog>

      {/* Remove review - requires typed confirmation */}
      <ReviewDialog
        open={removeReviewOpen}
        onOpenChange={(open) => {
          setRemoveReviewOpen(open);
          if (!open) setRemoveConfirmText("");
        }}
        title={`Remove ${addon.name}`}
        description="This will create a GitLab MR to delete the addon files from this cluster."
        onConfirm={() => removeMutation.mutate()}
        isPending={removeMutation.isPending}
        confirmDisabled={removeConfirmText !== addon.name}
        confirmLabel="Remove Addon"
        confirmVariant="destructive"
      >
        <div className="space-y-4">
          <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-sm space-y-2">
            <p>
              You are about to remove addon <strong>{addon.name}</strong> from cluster{" "}
              <strong>{clusterName}</strong>.
            </p>
            <p className="text-xs text-muted-foreground">
              This will delete the following files:
            </p>
            <ul className="text-xs font-mono text-muted-foreground list-disc list-inside">
              <li>mces/{mce}/{clusterName}/{addon.name}/{addon.name}.yaml</li>
              <li>mces/{mce}/{clusterName}/{addon.name}/values.yaml</li>
            </ul>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">
              Type <code className="bg-muted px-1.5 py-0.5 rounded text-destructive">{addon.name}</code> to confirm:
            </label>
            <input
              type="text"
              className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-destructive/50"
              value={removeConfirmText}
              onChange={(e) => setRemoveConfirmText(e.target.value)}
              placeholder={addon.name}
              autoComplete="off"
            />
            {removeConfirmText && removeConfirmText !== addon.name && (
              <p className="text-xs text-destructive">Name does not match</p>
            )}
          </div>
        </div>
      </ReviewDialog>
    </>
  );
}

// ── Available addon card ───────────────────────────────────────────────────────

function AvailableAddonCard({
  addon, clusterName, mce, isAdmin, selected, onSelectChange, selectionMode,
}: {
  addon: AddonCatalogEntry; clusterName: string; mce: string; isAdmin: boolean;
  selected?: boolean; onSelectChange?: (selected: boolean) => void; selectionMode?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("form");
  // Use current_version as default; if available_versions is empty, we'll add it as fallback
  const effectiveVersions = addon.available_versions.length > 0
    ? addon.available_versions
    : addon.current_version ? [addon.current_version] : ["main"];
  const [selectedVersion, setSelectedVersion] = useState(effectiveVersions[0] ?? "main");

  // Store ONLY the fields the user has explicitly changed (key → new value)
  // This is a Set of keys that were touched, plus their new values
  const [editedFields, setEditedFields] = useState<Map<string, unknown>>(new Map());
  const [yamlText, setYamlText] = useState("");
  const [yamlError, setYamlError] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: chartValues, isLoading: chartLoading } = useQuery<Record<string, unknown>>({
    queryKey: ["addons", addon.team, addon.name, "values", selectedVersion],
    queryFn: () =>
      api.get<Record<string, unknown>>(
        `/api/day2/addons/${addon.team}/${addon.name}/values?version=${selectedVersion}`
      ),
    enabled: expanded && Boolean(selectedVersion),
    staleTime: 300_000,
  });

  // Reset edits when version changes (user selects a different version)
  const prevVersionRef = useRef(selectedVersion);
  useEffect(() => {
    if (prevVersionRef.current !== selectedVersion) {
      setEditedFields(new Map());
      setYamlText("");
      setYamlError("");
      prevVersionRef.current = selectedVersion;
    }
  }, [selectedVersion]);

  // Base values = chart defaults + team defaults (the "pristine" state)
  const baseValues: Record<string, unknown> = useMemo(() => ({
    ...(chartValues ? flattenValues(chartValues) : {}),
    ...flattenValues(addon.default_values),
  }), [chartValues, addon.default_values]);

  // Display values = base values with edited fields applied
  const displayValues: Record<string, unknown> = useMemo(() => {
    const result = { ...baseValues };
    editedFields.forEach((value, key) => {
      result[key] = value;
    });
    return result;
  }, [baseValues, editedFields]);

  // Compute true overrides: only fields that were edited AND differ from base
  const overridesForSubmit: Record<string, unknown> = useMemo(() => {
    const overrides: Record<string, unknown> = {};
    editedFields.forEach((value, key) => {
      const baseVal = baseValues[key];
      // Compare as strings to handle type differences (boolean vs "true" string)
      const baseStr = String(baseVal ?? "");
      const valueStr = String(value ?? "");
      if (baseStr !== valueStr) {
        overrides[key] = value;
      }
    });
    return overrides;
  }, [editedFields, baseValues]);

  // Build the ArgoCD metadata OVERRIDES for the {addon}.yaml file
  // Only include fields that differ from team defaults
  const metadataOverrides: Record<string, unknown> = useMemo(() => {
    if (!addon.argocd_metadata) return {};
    const overrides: Record<string, unknown> = {};

    // Only include targetRevision if it differs from team default
    if (selectedVersion !== addon.argocd_metadata.targetRevision) {
      overrides.targetRevision = selectedVersion;
    }

    // Add other overridable fields here if needed in the future
    // e.g., syncPolicy, projectNamespace, etc.

    return overrides;
  }, [addon.argocd_metadata, selectedVersion]);

  const metadataYaml = Object.keys(metadataOverrides).length > 0
    ? jsYaml.dump(metadataOverrides, { indent: 2, lineWidth: -1 })
    : "";

  function handleViewModeChange(next: ViewMode) {
    if (next === "yaml") {
      // Show the full current values as YAML (what the form displays)
      setYamlText(jsYaml.dump(unflattenValues(displayValues), { indent: 2, lineWidth: -1 }));
      setYamlError("");
    } else {
      try {
        const parsed = (jsYaml.load(yamlText) as Record<string, unknown>) ?? {};
        // Sync YAML changes back to form - mark all parsed fields as edited
        const flat = flattenValues(parsed);
        setEditedFields(new Map(Object.entries(flat)));
        setYamlError("");
      } catch {
        setYamlError("Invalid YAML — fix errors before switching to form view");
        return;
      }
    }
    setViewMode(next);
  }

  function handleYamlChange(text: string) {
    setYamlText(text);
    try {
      const parsed = (jsYaml.load(text) as Record<string, unknown>) ?? {};
      // In YAML mode, the YAML content IS the override - replace editedFields entirely
      const flat = flattenValues(parsed);
      setEditedFields(new Map(Object.entries(flat)));
      setYamlError("");
    } catch {
      setYamlError("Invalid YAML");
    }
  }

  function handleFieldChange(key: string, newValue: unknown) {
    const baseVal = baseValues[key];

    // For complex values (arrays/objects), compare by JSON
    const isComplex = typeof newValue === "object" && newValue !== null;
    const isSameAsBase = isComplex
      ? JSON.stringify(newValue) === JSON.stringify(baseVal)
      : String(newValue ?? "") === String(baseVal ?? "");

    // Debug: log every field change to trace unexpected edits
    if (process.env.NODE_ENV === "development") {
      console.log(`[AddonInstall] Field change: ${key}`, {
        newValue,
        baseVal,
        isComplex,
        isSameAsBase,
      });
    }

    setEditedFields(prev => {
      const next = new Map(prev);
      if (isSameAsBase) {
        // Value matches base - remove from edits (not an override)
        next.delete(key);
      } else {
        // Keep complex values as-is, coerce simple values
        next.set(key, isComplex ? newValue : coerce(String(newValue ?? "")));
      }
      return next;
    });
  }

  function resetEdits() {
    setEditedFields(new Map());
    setYamlText("");
  }

  const overridesYaml = Object.keys(overridesForSubmit).length > 0
    ? jsYaml.dump(unflattenValues(overridesForSubmit), { sortKeys: true })
    : "{}";

  const installMutation = useMutation({
    mutationFn: () =>
      api.post<MRDetail>(
        `/api/day2/clusters/${clusterName}/addons/${addon.team}/${addon.name}?mce=${mce}`,
        { version: selectedVersion, override_values: unflattenValues(overridesForSubmit) }
      ),
    onSuccess: (mr) => {
      toast.success(`Install MR #${mr.iid} created: ${mr.title}`);
      setReviewOpen(false);
      setExpanded(false);
      resetEdits();
      queryClient.invalidateQueries({ queryKey: ["clusters", clusterName, "addons"] });
    },
    onError: () => toast.error("Failed to create install MR"),
  });

  return (
    <>
      <div className={cn(
        "group/card bg-card rounded-xl border shadow-sm overflow-hidden transition-all",
        selected && "ring-2 ring-primary border-primary/50"
      )}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3.5">
          <div className="flex items-center gap-3 min-w-0">
            {/* Selection checkbox - visible in selection mode or on hover when admin */}
            {isAdmin && onSelectChange && (
              <div className={cn(
                "transition-opacity",
                selectionMode || selected ? "opacity-100" : "opacity-0 group-hover/card:opacity-100"
              )}>
                <Checkbox
                  checked={selected ?? false}
                  onCheckedChange={onSelectChange}
                />
              </div>
            )}
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/8 dark:bg-primary/15 shrink-0">
              <Package className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold truncate">{addon.name}</p>
              <p className="text-xs text-muted-foreground">{addon.team}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 ml-3 shrink-0">
            <span className="rounded-full px-2 py-0.5 text-xs font-mono text-muted-foreground bg-muted">
              {addon.current_version}
            </span>
            {expanded ? (
              <button
                onClick={() => setExpanded(false)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1"
              >
                Cancel
              </button>
            ) : isAdmin && !selectionMode ? (
              <button
                onClick={() => setExpanded(true)}
                className={cn(buttonVariants({ size: "sm" }), "gap-1.5 h-7")}
              >
                <Plus className="h-3.5 w-3.5" />Install
              </button>
            ) : null}
          </div>
        </div>

        {/* Install form */}
        {expanded && (
          <div className="border-t bg-muted/10 p-4 space-y-4">
            {/* Version selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Version</label>
              <select
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                value={selectedVersion}
                onChange={(e) => setSelectedVersion(e.target.value)}
              >
                {effectiveVersions.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </div>

            {/* Values */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  {chartLoading ? "Values (loading…)" : "Values (edit to override defaults)"}
                </p>
                {!chartLoading && <ViewToggle mode={viewMode} onChange={handleViewModeChange} />}
              </div>
              {chartLoading ? (
                <div className="space-y-1.5">
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ) : viewMode === "form" ? (
                <ValuesTable
                  entries={Object.entries(displayValues)}
                  onChange={(k, val) => handleFieldChange(k, coerce(val))}
                  onComplexChange={(k, val) => handleFieldChange(k, val)}
                />
              ) : (
                <div className="space-y-1">
                  <textarea
                    className={cn(
                      "w-full rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow",
                      yamlError && "border-destructive/50"
                    )}
                    rows={Math.max(8, yamlText.split("\n").length + 1)}
                    value={yamlText}
                    onChange={(e) => handleYamlChange(e.target.value)}
                    spellCheck={false}
                  />
                  {yamlError && (
                    <p className="text-xs text-destructive">{yamlError}</p>
                  )}
                </div>
              )}
              {editedFields.size > 0 && viewMode === "form" && (
                <div className="flex items-center justify-between mt-1">
                  <p className="text-xs text-primary/70">
                    {Object.keys(overridesForSubmit).length} override{Object.keys(overridesForSubmit).length !== 1 ? "s" : ""} will be saved
                    {editedFields.size > Object.keys(overridesForSubmit).length && (
                      <span className="text-muted-foreground ml-1">
                        ({editedFields.size - Object.keys(overridesForSubmit).length} unchanged)
                      </span>
                    )}
                  </p>
                  <button
                    type="button"
                    onClick={resetEdits}
                    className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                  >
                    Reset
                  </button>
                </div>
              )}
            </div>

            <button
              onClick={() => setReviewOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-primary/90 transition-colors"
            >
              <Eye className="h-3.5 w-3.5" />
              Review & Install
            </button>
          </div>
        )}
      </div>

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title={`Review: Install ${addon.name}`}
        description="Files that will be created are shown below. Green lines are new content. Confirming creates a GitLab MR for approval."
        onConfirm={() => installMutation.mutate()}
        isPending={installMutation.isPending}
      >
        <div className="space-y-4">
          {/* Summary */}
          <div className="text-sm space-y-1">
            <div className="flex gap-3">
              <span className="text-muted-foreground w-20 shrink-0">Addon</span>
              <span className="font-semibold">{addon.name}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-20 shrink-0">Version</span>
              <span className="font-medium">{selectedVersion}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-20 shrink-0">Team</span>
              <span className="font-medium">{addon.team}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-20 shrink-0">Cluster</span>
              <span className="font-medium">{clusterName}</span>
            </div>
          </div>

          {/* File previews */}
          <div className="space-y-3">
            {/* {addon}.yaml - ArgoCD metadata - ALWAYS show */}
            <div className="space-y-1">
              <p className="text-xs font-semibold text-muted-foreground">
                <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-status-ready/10 text-status-ready mr-1.5">NEW</span>
                <code className="text-foreground font-mono text-[11px]">mces/{mce}/{clusterName}/{addon.name}/{addon.name}.yaml</code>
              </p>
              {Object.keys(metadataOverrides).length === 0 ? (
                <div className="rounded-lg bg-muted/30 border border-dashed p-3 text-xs text-muted-foreground italic text-center">
                  Empty file — using team default version ({addon.argocd_metadata?.targetRevision || "N/A"})
                </div>
              ) : (
                <pre className="rounded-lg bg-muted/50 border p-3 text-xs font-mono overflow-x-auto whitespace-pre">
                  {metadataYaml.split("\n").filter(Boolean).map((line, i) => (
                    <div key={i} className="text-status-ready">+ {line}</div>
                  ))}
                </pre>
              )}
            </div>

            {/* values.yaml - cluster overrides */}
            <div className="space-y-1">
              <p className="text-xs font-semibold text-muted-foreground">
                <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-status-ready/10 text-status-ready mr-1.5">NEW</span>
                <code className="text-foreground font-mono text-[11px]">mces/{mce}/{clusterName}/{addon.name}/values.yaml</code>
              </p>
              {Object.keys(overridesForSubmit).length === 0 ? (
                <div className="rounded-lg bg-muted/30 border border-dashed p-3 text-xs text-muted-foreground italic text-center">
                  Empty file — no overrides needed, using team/chart defaults
                </div>
              ) : (
                <pre className="rounded-lg bg-muted/50 border p-3 text-xs font-mono overflow-x-auto whitespace-pre">
                  {overridesYaml.split("\n").filter(Boolean).map((line, i) => (
                    <div key={i} className="text-status-ready">+ {line}</div>
                  ))}
                </pre>
              )}
            </div>
          </div>

          {/* Debug info - remove in production */}
          {process.env.NODE_ENV === "development" && (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">Debug: override computation</summary>
              <pre className="mt-1 p-2 bg-muted/30 rounded text-[10px] overflow-auto">
                editedFields: {editedFields.size} keys{"\n"}
                overrides: {Object.keys(overridesForSubmit).length} keys{"\n"}
                has argocd_metadata: {String(Boolean(addon.argocd_metadata))}{"\n"}
                editedKeys: {[...editedFields.keys()].join(", ") || "(none)"}{"\n"}
                overrideKeys: {Object.keys(overridesForSubmit).join(", ") || "(none)"}
              </pre>
            </details>
          )}
        </div>
      </ReviewDialog>
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

// ── Bulk Install Dialog ────────────────────────────────────────────────────────

interface BulkInstallItem {
  addon: AddonCatalogEntry;
  selectedVersion: string;
  overrides: Record<string, unknown>;
}

// Separate modal for configuring a single addon's values
function AddonConfigModal({
  open,
  onOpenChange,
  addon,
  selectedVersion,
  currentOverrides,
  onVersionChange,
  onSave,
  stepInfo,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  addon: AddonCatalogEntry;
  selectedVersion: string;
  currentOverrides: Record<string, unknown>;
  onVersionChange: (version: string) => void;
  onSave: (overrides: Record<string, unknown>) => void;
  stepInfo?: { current: number; total: number };
}) {
  const [viewMode, setViewMode] = useState<ViewMode>("form");
  const [editedFields, setEditedFields] = useState<Map<string, unknown>>(() => {
    // Initialize from existing overrides
    const map = new Map<string, unknown>();
    for (const [k, v] of Object.entries(flattenValues(currentOverrides))) {
      map.set(k, v);
    }
    return map;
  });
  const [yamlText, setYamlText] = useState("");
  const [yamlError, setYamlError] = useState("");

  const effectiveVersions = addon.available_versions.length > 0
    ? addon.available_versions
    : addon.current_version ? [addon.current_version] : ["main"];

  // Fetch chart values for selected version
  const { data: chartValues, isLoading: chartLoading } = useQuery<Record<string, unknown>>({
    queryKey: ["addons", addon.team, addon.name, "values", selectedVersion],
    queryFn: () =>
      api.get<Record<string, unknown>>(
        `/api/day2/addons/${addon.team}/${addon.name}/values?version=${selectedVersion}`
      ),
    enabled: open && Boolean(selectedVersion),
    staleTime: 300_000,
  });

  // Base values = chart defaults + team defaults
  const baseValues: Record<string, unknown> = useMemo(() => ({
    ...(chartValues ? flattenValues(chartValues) : {}),
    ...flattenValues(addon.default_values),
  }), [chartValues, addon.default_values]);

  // Display values = base + edited fields
  const displayValues: Record<string, unknown> = useMemo(() => {
    const result = { ...baseValues };
    editedFields.forEach((value, key) => {
      result[key] = value;
    });
    return result;
  }, [baseValues, editedFields]);

  // Compute true overrides (only fields that differ from base)
  const computedOverrides = useMemo(() => {
    const overrides: Record<string, unknown> = {};
    editedFields.forEach((value, key) => {
      const baseVal = baseValues[key];
      const baseStr = String(baseVal ?? "");
      const valueStr = String(value ?? "");
      if (baseStr !== valueStr) {
        overrides[key] = value;
      }
    });
    return overrides;
  }, [editedFields, baseValues]);

  function handleFieldChange(key: string, newValue: unknown) {
    const baseVal = baseValues[key];

    // For complex values (arrays/objects), compare by JSON
    const isComplex = typeof newValue === "object" && newValue !== null;
    const isSameAsBase = isComplex
      ? JSON.stringify(newValue) === JSON.stringify(baseVal)
      : String(newValue ?? "") === String(baseVal ?? "");

    setEditedFields(prev => {
      const next = new Map(prev);
      if (isSameAsBase) {
        next.delete(key);
      } else {
        // Keep complex values as-is, coerce simple values
        next.set(key, isComplex ? newValue : coerce(String(newValue ?? "")));
      }
      return next;
    });
  }

  function handleViewModeChange(next: ViewMode) {
    if (next === "yaml") {
      // Show the full current values (what the form displays)
      setYamlText(jsYaml.dump(unflattenValues(displayValues), { indent: 2, lineWidth: -1 }));
      setYamlError("");
    } else {
      try {
        const parsed = (jsYaml.load(yamlText) as Record<string, unknown>) ?? {};
        const flat = flattenValues(parsed);
        setEditedFields(new Map(Object.entries(flat)));
        setYamlError("");
      } catch {
        setYamlError("Invalid YAML — fix errors before switching to form view");
        return;
      }
    }
    setViewMode(next);
  }

  function handleYamlChange(text: string) {
    setYamlText(text);
    try {
      const parsed = (jsYaml.load(text) as Record<string, unknown>) ?? {};
      setEditedFields(new Map(Object.entries(flattenValues(parsed))));
      setYamlError("");
    } catch {
      setYamlError("Invalid YAML");
    }
  }

  function handleSave() {
    onSave(unflattenValues(computedOverrides));
    onOpenChange(false);
  }

  const overrideCount = Object.keys(computedOverrides).length;

  return (
    <SharedReviewDialog
      open={open}
      onOpenChange={onOpenChange}
      title={stepInfo ? `Configure: ${addon.name} (${stepInfo.current}/${stepInfo.total})` : `Configure: ${addon.name}`}
      description="Set version and override values for this addon. Only changed values will be saved."
      onConfirm={handleSave}
      isPending={false}
      confirmLabel={`Save & Continue${overrideCount > 0 ? ` (${overrideCount} override${overrideCount !== 1 ? "s" : ""})` : ""}`}
      size="lg"
    >
      <div className="space-y-4">
        {/* Version selector */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Version</label>
          <select
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            value={selectedVersion}
            onChange={(e) => {
              onVersionChange(e.target.value);
              setEditedFields(new Map()); // Reset edits when version changes
            }}
          >
            {effectiveVersions.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </div>

        {/* Values editor */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              {chartLoading ? "Values (loading...)" : "Values"}
            </label>
            {!chartLoading && <ViewToggle mode={viewMode} onChange={handleViewModeChange} />}
          </div>

          {chartLoading ? (
            <div className="space-y-1.5">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : viewMode === "form" ? (
            <div className="max-h-[40vh] overflow-y-auto">
              <ValuesTable
                entries={Object.entries(displayValues)}
                onChange={(k, val) => handleFieldChange(k, coerce(val))}
                onComplexChange={(k, val) => handleFieldChange(k, val)}
              />
            </div>
          ) : (
            <div className="space-y-1">
              <textarea
                className={cn(
                  "w-full rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow",
                  yamlError && "border-destructive/50"
                )}
                rows={Math.max(10, yamlText.split("\n").length + 1)}
                value={yamlText}
                onChange={(e) => handleYamlChange(e.target.value)}
                spellCheck={false}
              />
              {yamlError && <p className="text-xs text-destructive">{yamlError}</p>}
            </div>
          )}

          {overrideCount > 0 && (
            <div className="flex items-center justify-between">
              <p className="text-xs text-primary/70">
                {overrideCount} override{overrideCount !== 1 ? "s" : ""} will be saved
              </p>
              <button
                type="button"
                onClick={() => setEditedFields(new Map())}
                className="text-xs text-muted-foreground hover:text-destructive transition-colors"
              >
                Reset All
              </button>
            </div>
          )}
        </div>
      </div>
    </SharedReviewDialog>
  );
}

function BulkInstallDialog({
  open,
  onOpenChange,
  items,
  onVersionChange,
  onOverridesChange,
  clusterName,
  mce,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: BulkInstallItem[];
  onVersionChange: (addonKey: string, version: string) => void;
  onOverridesChange: (addonKey: string, overrides: Record<string, unknown>) => void;
  clusterName: string;
  mce: string;
  onSuccess: () => void;
}) {
  const queryClient = useQueryClient();
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; errors: string[] }>({
    done: 0,
    total: 0,
    errors: [],
  });
  // Track which addon's config modal is open (null = none)
  const [configOpenFor, setConfigOpenFor] = useState<string | null>(null);
  // Review phase: shows all files before final submission
  const [reviewPhase, setReviewPhase] = useState(false);

  async function handleBulkInstall() {
    setInstalling(true);
    setProgress({ done: 0, total: items.length, errors: [] });

    // Group items by team (bulk install only supports single team per MR)
    const itemsByTeam = new Map<string, typeof items>();
    for (const item of items) {
      const team = item.addon.team;
      if (!itemsByTeam.has(team)) {
        itemsByTeam.set(team, []);
      }
      itemsByTeam.get(team)!.push(item);
    }

    const errors: string[] = [];
    const errorMessages: string[] = [];
    let totalDone = 0;

    // Create one MR per team
    for (const teamItems of itemsByTeam.values()) {
      try {
        const payload = {
          addons: teamItems.map(({ addon, selectedVersion, overrides }) => ({
            team: addon.team,
            addon: addon.name,
            version: selectedVersion,
            override_values: overrides,
          })),
        };

        await api.post<MRDetail>(
          `/api/day2/clusters/${clusterName}/addons/bulk?mce=${mce}`,
          payload
        );

        totalDone += teamItems.length;
        setProgress((p) => ({ ...p, done: totalDone }));
      } catch (err) {
        errors.push(...teamItems.map(i => i.addon.name));
        // Capture actual error message for debugging
        const msg = err instanceof Error ? err.message : String(err);
        if (!errorMessages.includes(msg)) errorMessages.push(msg);
      }
    }

    setProgress((p) => ({ ...p, errors }));

    if (errors.length === 0) {
      const mrCount = itemsByTeam.size;
      const mrMsg = mrCount > 1
        ? `${mrCount} MRs (one per team)`
        : "1 MR";
      toast.success(`${items.length} addon${items.length > 1 ? "s" : ""} added to ${mrMsg}`);
      queryClient.invalidateQueries({ queryKey: ["clusters", clusterName, "addons"] });
      onSuccess();
      onOpenChange(false);
    } else if (totalDone > 0) {
      toast.success(`${totalDone} of ${items.length} addons added`);
      toast.error(`Failed: ${errors.join(", ")}`);
      if (errorMessages.length > 0) {
        toast.error(errorMessages[0], { duration: 10000 });
      }
      queryClient.invalidateQueries({ queryKey: ["clusters", clusterName, "addons"] });
    } else {
      // Show actual error message to help with debugging
      const errMsg = errorMessages.length > 0 ? errorMessages[0] : "Unknown error";
      toast.error(`Failed to create addon MR: ${errMsg}`, { duration: 10000 });
    }

    setInstalling(false);
  }

  const totalOverrides = items.reduce((sum, item) => sum + Object.keys(item.overrides).length, 0);
  const configuredCount = items.filter(i => Object.keys(i.overrides).length > 0).length;

  // Find which item is being configured and its position
  const configItemIndex = configOpenFor ? items.findIndex(i => `${i.addon.team}/${i.addon.name}` === configOpenFor) : -1;
  const configItem = configItemIndex >= 0 ? items[configItemIndex] : null;

  // Reset review phase when dialog closes
  const handleClose = (isOpen: boolean) => {
    if (!isOpen) {
      setReviewPhase(false);
    }
    onOpenChange(isOpen);
  };

  return (
    <>
      {/* Phase 1: Configuration */}
      <SharedReviewDialog
        open={open && !configOpenFor && !reviewPhase}
        onOpenChange={handleClose}
        title={`Bulk Install: ${items.length} Addon${items.length !== 1 ? "s" : ""}`}
        description="Click 'Configure' to set version and values for each addon. Click 'Review' when ready."
        onConfirm={() => setReviewPhase(true)}
        isPending={false}
        confirmLabel="Review & Install →"
      >
        <div className="space-y-2 max-h-[50vh] overflow-y-auto">
          {items.map((item) => {
            const addonKey = `${item.addon.team}/${item.addon.name}`;
            const overrideCount = Object.keys(item.overrides).length;
            const isConfigured = overrideCount > 0;

            return (
              <div key={addonKey} className={cn(
                "flex items-center gap-3 p-3 rounded-lg border transition-colors",
                isConfigured ? "bg-status-ready/5 border-status-ready/30" : "bg-amber-500/5 border-amber-500/30"
              )}>
                {/* Step number / status icon */}
                <div className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold shrink-0",
                  isConfigured ? "bg-status-ready text-white" : "bg-amber-500/20 text-amber-600"
                )}>
                  {isConfigured ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                </div>
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 shrink-0">
                  <Package className="h-4 w-4 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold truncate">{item.addon.name}</p>
                  <p className="text-xs text-muted-foreground">{item.addon.team}</p>
                </div>
                <div className="flex items-center gap-2">
                  {isConfigured ? (
                    <span className="text-xs text-status-ready font-medium">
                      {overrideCount} override{overrideCount !== 1 ? "s" : ""}
                    </span>
                  ) : (
                    <span className="text-xs text-amber-600 font-medium">
                      Using defaults
                    </span>
                  )}
                  <span className="text-xs font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                    {item.selectedVersion}
                  </span>
                  <button
                    type="button"
                    onClick={() => setConfigOpenFor(addonKey)}
                    className={cn(buttonVariants({ variant: isConfigured ? "outline" : "default", size: "xs" }), "gap-1")}
                  >
                    {isConfigured ? "Edit" : "Configure"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Summary / Warning */}
        {configuredCount < items.length ? (
          <div className="mt-4 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-xs">
                <p className="font-medium text-amber-700 dark:text-amber-500">
                  {items.length - configuredCount} addon{items.length - configuredCount !== 1 ? "s" : ""} not configured
                </p>
                <p className="text-muted-foreground mt-0.5">
                  These addons will be installed with default values. Click &quot;Configure&quot; to customize.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-4 p-3 rounded-lg border border-status-ready/30 bg-status-ready/5">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-status-ready shrink-0" />
              <p className="text-xs text-status-ready font-medium">
                All {items.length} addons configured ({totalOverrides} total override{totalOverrides !== 1 ? "s" : ""})
              </p>
            </div>
          </div>
        )}
      </SharedReviewDialog>

      {/* Phase 2: Review all files */}
      <SharedReviewDialog
        open={open && reviewPhase && !installing}
        onOpenChange={(isOpen) => {
          if (!isOpen) setReviewPhase(false);
        }}
        title="Review: Files to Create"
        description={`${items.length} MRs will be created with the following files. Confirm to submit.`}
        onConfirm={handleBulkInstall}
        isPending={installing}
        confirmLabel={`Create ${items.length} MR${items.length !== 1 ? "s" : ""}`}
        size="lg"
      >
        {/* Warning banner if any addons using defaults */}
        {configuredCount < items.length && (
          <div className="mb-4 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-xs">
                <p className="font-medium text-amber-700 dark:text-amber-500">
                  {items.length - configuredCount} addon{items.length - configuredCount !== 1 ? "s" : ""} will use default values
                </p>
                <p className="text-muted-foreground mt-0.5">
                  Go back to configure custom values if needed.
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="space-y-4 max-h-[55vh] overflow-y-auto">
          {items.map((item) => {
            const overrideCount = Object.keys(item.overrides).length;
            const overridesYaml = overrideCount > 0
              ? jsYaml.dump(item.overrides, { indent: 2, lineWidth: -1 })
              : "";

            return (
              <div key={`${item.addon.team}/${item.addon.name}`} className={cn(
                "rounded-lg border overflow-hidden",
                overrideCount === 0 && "border-amber-500/30"
              )}>
                {/* Addon header */}
                <div className={cn(
                  "flex items-center gap-3 p-3 border-b",
                  overrideCount === 0 ? "bg-amber-500/5" : "bg-muted/30"
                )}>
                  <Package className="h-4 w-4 text-primary" />
                  <span className="font-semibold text-sm">{item.addon.name}</span>
                  <span className="text-xs text-muted-foreground">({item.addon.team})</span>
                  {overrideCount === 0 && (
                    <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-500/10 px-1.5 py-0.5 rounded">
                      <AlertTriangle className="h-3 w-3" />
                      Using defaults
                    </span>
                  )}
                  <span className="ml-auto text-xs font-mono bg-muted px-1.5 py-0.5 rounded">{item.selectedVersion}</span>
                </div>

                {/* Files */}
                <div className="p-3 space-y-3 text-xs">
                  {/* {addon}.yaml */}
                  <div>
                    <p className="font-mono text-muted-foreground mb-1">
                      <span className="text-status-ready">[NEW]</span> mces/{mce}/{clusterName}/{item.addon.name}/{item.addon.name}.yaml
                    </p>
                    <pre className="bg-muted/50 rounded p-2 font-mono overflow-x-auto">
                      <span className="text-status-ready">+ targetRevision: {item.selectedVersion}</span>
                    </pre>
                  </div>

                  {/* values.yaml */}
                  <div>
                    <p className="font-mono text-muted-foreground mb-1">
                      <span className="text-status-ready">[NEW]</span> mces/{mce}/{clusterName}/{item.addon.name}/values.yaml
                    </p>
                    {overrideCount === 0 ? (
                      <p className="text-muted-foreground italic bg-muted/50 rounded p-2">Empty file — using defaults</p>
                    ) : (
                      <pre className="bg-muted/50 rounded p-2 font-mono overflow-x-auto max-h-32">
                        {overridesYaml.split("\n").filter(Boolean).map((line, i) => (
                          <div key={i} className="text-status-ready">+ {line}</div>
                        ))}
                      </pre>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Back button */}
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setReviewPhase(false)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Back to configuration
          </button>
        </div>
      </SharedReviewDialog>

      {/* Phase 3: Progress */}
      {installing && (
        <SharedReviewDialog
          open={true}
          onOpenChange={() => {}}
          title="Creating MRs..."
          description="Please wait while merge requests are being created."
          onConfirm={() => {}}
          isPending={true}
          confirmLabel=""
        >
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              Creating MRs... {progress.done}/{progress.total}
            </div>
            <div className="w-full bg-muted rounded-full h-2">
              <div
                className="bg-primary h-2 rounded-full transition-all"
                style={{ width: `${(progress.done / progress.total) * 100}%` }}
              />
            </div>
            {progress.errors.length > 0 && (
              <p className="text-xs text-destructive">
                Failed: {progress.errors.join(", ")}
              </p>
            )}
          </div>
        </SharedReviewDialog>
      )}

      {/* Separate config modal for each addon */}
      {configItem && (
        <AddonConfigModal
          open={true}
          onOpenChange={(isOpen) => {
            if (!isOpen) setConfigOpenFor(null);
          }}
          addon={configItem.addon}
          selectedVersion={configItem.selectedVersion}
          currentOverrides={configItem.overrides}
          onVersionChange={(v) => onVersionChange(configOpenFor!, v)}
          onSave={(o) => onOverridesChange(configOpenFor!, o)}
          stepInfo={{ current: configItemIndex + 1, total: items.length }}
        />
      )}
    </>
  );
}

// ── Bulk Action Bar ────────────────────────────────────────────────────────────

function BulkActionBar({
  selectedCount,
  onClear,
  onInstall,
}: {
  selectedCount: number;
  onClear: () => void;
  onInstall: () => void;
}) {
  if (selectedCount === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 duration-200">
      <div className="flex items-center gap-3 bg-card border shadow-lg rounded-xl px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground text-sm font-bold">
            {selectedCount}
          </div>
          <span className="text-sm font-medium">
            addon{selectedCount !== 1 ? "s" : ""} selected
          </span>
        </div>
        <div className="h-5 w-px bg-border" />
        <button
          onClick={onClear}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
          Clear
        </button>
        <button
          onClick={onInstall}
          className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}
        >
          <Plus className="h-3.5 w-3.5" />
          Install Selected
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

function ClusterAddonsContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const clusterName = params.name as string;
  const mceParam = searchParams.get("mce") ?? "";
  const siteParam = searchParams.get("site") ?? "";
  const isAdmin = useIsAdmin();
  const queryClient = useQueryClient();

  // Bulk selection state
  const [selectedAddons, setSelectedAddons] = useState<Set<string>>(new Set());
  const [bulkVersions, setBulkVersions] = useState<Record<string, string>>({});
  const [bulkOverrides, setBulkOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false);

  const toggleAddonSelection = useCallback((addonKey: string, addon: AddonCatalogEntry) => {
    setSelectedAddons((prev) => {
      const next = new Set(prev);
      if (next.has(addonKey)) {
        next.delete(addonKey);
      } else {
        next.add(addonKey);
        // Set default version when selecting
        if (!bulkVersions[addonKey]) {
          const defaultVersion = addon.available_versions[0] ?? addon.current_version ?? "main";
          setBulkVersions((v) => ({ ...v, [addonKey]: defaultVersion }));
        }
        // Initialize empty overrides
        if (!bulkOverrides[addonKey]) {
          setBulkOverrides((o) => ({ ...o, [addonKey]: {} }));
        }
      }
      return next;
    });
  }, [bulkVersions, bulkOverrides]);

  const clearSelection = useCallback(() => {
    setSelectedAddons(new Set());
    setBulkVersions({});
    setBulkOverrides({});
  }, []);

  const { data: clusterList } = useQuery<ClusterStatus[]>({
    queryKey: ["clusters"],
    queryFn: () => api.get<ClusterStatus[]>("/api/day1/clusters"),
    enabled: !mceParam,
    staleTime: 30_000,
  });

  const resolvedCluster = !mceParam ? clusterList?.find((c) => c.name === clusterName) : null;
  const mce = mceParam || resolvedCluster?.mce || "";
  const site = siteParam || resolvedCluster?.site || "";

  const { data: installedData, isLoading: installedLoading, isFetching: fetchingInstalled, error } = useQuery<ClusterInstalledResponse>({
    queryKey: ["clusters", clusterName, "addons"],
    queryFn: () =>
      api.get<ClusterInstalledResponse>(`/api/day2/clusters/${clusterName}/addons?mce=${mce}`),
    enabled: Boolean(mce),
    staleTime: 30_000,
  });

  const { data: catalog, isLoading: catalogLoading, isFetching: fetchingCatalog } = useQuery<AddonCatalogEntry[]>({
    queryKey: ["addons", "catalog"],
    queryFn: () => api.get<AddonCatalogEntry[]>("/api/day2/addons"),
    staleTime: 120_000,
  });

  const { data: gitlabInfo } = useQuery<{ sigs_group_url: string }>({
    queryKey: ["day2", "gitlab-info"],
    queryFn: () => api.get<{ sigs_group_url: string }>("/api/day2/gitlab-info"),
    staleTime: 300_000, // 5 min - rarely changes
  });

  const isFetching = fetchingInstalled || fetchingCatalog;

  const installed = installedData?.installed ?? [];
  const installedKeys = new Set(installed.map((a) => `${a.team}/${a.name}`));
  const available = (catalog ?? []).filter((a) => !installedKeys.has(`${a.team}/${a.name}`));
  const isLoading = installedLoading || catalogLoading || (!mceParam && !mce);

  // Group helpers
  function groupByTeam<T extends { team: string }>(items: T[]): [string, T[]][] {
    const map: Record<string, T[]> = {};
    for (const item of items) {
      (map[item.team] ??= []).push(item);
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }

  return (
    <div className={cn("p-6 lg:p-8 max-w-4xl mx-auto space-y-8", selectedAddons.size > 0 && "pb-24")}>
      {/* Page header */}
      <div className="flex items-center gap-3">
        <Link
          href={`/clusters/${clusterName}?site=${site}&mce=${mce}`}
          className={buttonVariants({ variant: "ghost", size: "icon" })}
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            {clusterName} — Addons
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {installed.length > 0
              ? `${installed.length} installed · ${available.length} available`
              : "Manage installed and available addons for this cluster"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {gitlabInfo?.sigs_group_url && (
            <a
              href={gitlabInfo.sigs_group_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
              title="View SIGs group in GitLab"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              GitLab
            </a>
          )}
          <button
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ["clusters", clusterName, "addons"] });
              queryClient.invalidateQueries({ queryKey: ["addons", "catalog"] });
            }}
            disabled={isFetching}
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
            title="Refresh addons"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load addons. Please try again.
        </div>
      ) : isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
        </div>
      ) : (
        <div className="space-y-10">

          {/* ── Installed ──────────────────────────────────────────────────── */}
          <section className="space-y-4">
            <div className="flex items-center gap-2 pb-1 border-b">
              <h2 className="text-sm font-bold uppercase tracking-wider text-foreground">
                Installed
              </h2>
              <span className="rounded-full bg-[#00c875]/10 text-[#007038] dark:text-[#00c875] px-2 py-0.5 text-xs font-semibold">
                {installed.length}
              </span>
            </div>

            {installed.length === 0 ? (
              <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                No addons installed on this cluster yet.
              </div>
            ) : (
              <div className="space-y-6">
                {groupByTeam(installed).map(([team, addons]) => (
                  <div key={team} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Users className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{team}</span>
                      <span className="text-xs text-muted-foreground">({addons.length})</span>
                    </div>
                    <div className="space-y-2 pl-5">
                      {addons.map((addon) => (
                        <InstalledAddonCard
                          key={`${addon.team}/${addon.name}`}
                          addon={addon}
                          clusterName={clusterName}
                          mce={mce}
                          isAdmin={isAdmin}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Available ──────────────────────────────────────────────────── */}
          {available.length > 0 && (
            <section className="space-y-4">
              <div className="flex items-center justify-between pb-1 border-b">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-bold uppercase tracking-wider text-foreground">
                    Available
                  </h2>
                  <span className="rounded-full bg-primary/10 text-primary px-2 py-0.5 text-xs font-semibold">
                    {available.length}
                  </span>
                </div>
                {isAdmin && (
                  <button
                    onClick={() => {
                      if (selectedAddons.size === available.length) {
                        clearSelection();
                      } else {
                        const newSelected = new Set<string>();
                        const newVersions: Record<string, string> = {};
                        const newOverrides: Record<string, Record<string, unknown>> = {};
                        for (const addon of available) {
                          const key = `${addon.team}/${addon.name}`;
                          newSelected.add(key);
                          newVersions[key] = addon.available_versions[0] ?? addon.current_version ?? "main";
                          newOverrides[key] = {};
                        }
                        setSelectedAddons(newSelected);
                        setBulkVersions(newVersions);
                        setBulkOverrides(newOverrides);
                      }
                    }}
                    className="text-xs text-muted-foreground hover:text-primary transition-colors"
                  >
                    {selectedAddons.size === available.length ? "Deselect All" : "Select All"}
                  </button>
                )}
              </div>

              <div className="space-y-6">
                {groupByTeam(available).map(([team, addons]) => (
                  <div key={team} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Users className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{team}</span>
                      <span className="text-xs text-muted-foreground">({addons.length})</span>
                    </div>
                    <div className="space-y-2 pl-5">
                      {addons.map((addon) => {
                        const addonKey = `${addon.team}/${addon.name}`;
                        return (
                          <AvailableAddonCard
                            key={addonKey}
                            addon={addon}
                            clusterName={clusterName}
                            mce={mce}
                            isAdmin={isAdmin}
                            selected={selectedAddons.has(addonKey)}
                            onSelectChange={() => toggleAddonSelection(addonKey, addon)}
                            selectionMode={selectedAddons.size > 0}
                          />
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

        </div>
      )}

      {/* Bulk action bar */}
      <BulkActionBar
        selectedCount={selectedAddons.size}
        onClear={clearSelection}
        onInstall={() => setBulkDialogOpen(true)}
      />

      {/* Bulk install dialog */}
      <BulkInstallDialog
        open={bulkDialogOpen}
        onOpenChange={setBulkDialogOpen}
        items={Array.from(selectedAddons).map((key) => {
          const addon = available.find((a) => `${a.team}/${a.name}` === key)!;
          return {
            addon,
            selectedVersion: bulkVersions[key] ?? addon.available_versions[0] ?? addon.current_version ?? "main",
            overrides: bulkOverrides[key] ?? {},
          };
        }).filter((item) => item.addon)}
        onVersionChange={(key, version) => setBulkVersions((v) => ({ ...v, [key]: version }))}
        onOverridesChange={(key, overrides) => setBulkOverrides((o) => ({ ...o, [key]: overrides }))}
        clusterName={clusterName}
        mce={mce}
        onSuccess={clearSelection}
      />
    </div>
  );
}

export default function ClusterAddonsPage() {
  return (
    <Suspense>
      <ClusterAddonsContent />
    </Suspense>
  );
}
