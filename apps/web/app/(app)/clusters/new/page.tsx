"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CheckCircle2, Eye, Plus, Trash2, Code, List, FileText } from "lucide-react";
import { toast } from "sonner";
import jsYaml from "js-yaml";
import { api } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ReviewDialog } from "@/components/common/review-dialog";
import { useIsAdmin } from "@/stores/auth-store";
import type { ClusterSpec, MRDetail, SpecVariable, OverrideableField } from "@/types";

const CREATE_NEW = "__create_new__";

// Variables handled by Cluster Identity section — filter from Spec Variables
const IDENTITY_VARIABLES = new Set([
  "cluster_name",
  "site_name",
  "site",
  "mce_name",
  "mce",
]);

function formatVariableName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Variable field ─────────────────────────────────────────────────────────────

function VariableField({
  variable, value, onChange,
}: {
  variable: SpecVariable; value: unknown; onChange: (v: unknown) => void;
}) {
  const base =
    "w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow";

  if (variable.type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id={variable.name}
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4 rounded border-border text-primary"
        />
        <label htmlFor={variable.name} className="text-sm text-muted-foreground">
          {variable.description ?? variable.name}
        </label>
      </div>
    );
  }

  if (variable.enum) {
    return (
      <Select value={String(value ?? "")} onValueChange={(v) => onChange(v ?? "")}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select…" />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {variable.enum.map((opt) => (
            <SelectItem key={opt} value={opt}>{opt}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  if (variable.type === "integer") {
    return (
      <input
        type="number"
        className={base}
        value={String(value ?? "")}
        min={variable.minimum}
        max={variable.maximum}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      />
    );
  }

  return (
    <input
      type="text"
      className={base}
      value={String(value ?? "")}
      placeholder={variable.description ?? variable.name}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// ── Array Item Editor ──────────────────────────────────────────────────────────

function ArrayItemEditor({
  item,
  index,
  onUpdate,
  onRemove,
}: {
  item: unknown;
  index: number;
  onUpdate: (value: unknown) => void;
  onRemove: () => void;
}) {
  const isObject = item !== null && typeof item === "object" && !Array.isArray(item);
  const itemObj = isObject ? (item as Record<string, unknown>) : null;

  if (itemObj) {
    return (
      <div className="rounded-lg border bg-muted/30 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">Item {index + 1}</span>
          <button
            type="button"
            onClick={onRemove}
            className="text-muted-foreground hover:text-destructive transition-colors p-1"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="grid gap-2">
          {Object.entries(itemObj).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-xs text-muted-foreground w-24 shrink-0 truncate">{key}</label>
              {typeof val === "boolean" ? (
                <input
                  type="checkbox"
                  checked={val}
                  onChange={(e) => onUpdate({ ...itemObj, [key]: e.target.checked })}
                  className="h-4 w-4 rounded border-border text-primary"
                />
              ) : Array.isArray(val) ? (
                <input
                  type="text"
                  className="flex-1 rounded border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-primary/50"
                  value={val.join(", ")}
                  onChange={(e) => onUpdate({ ...itemObj, [key]: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })}
                  placeholder="comma-separated values"
                />
              ) : (
                <input
                  type={typeof val === "number" ? "number" : "text"}
                  className="flex-1 rounded border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-primary/50"
                  value={String(val ?? "")}
                  onChange={(e) => onUpdate({ ...itemObj, [key]: typeof val === "number" ? Number(e.target.value) : e.target.value })}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        className="flex-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
        value={String(item ?? "")}
        onChange={(e) => onUpdate(e.target.value)}
      />
      <button
        type="button"
        onClick={onRemove}
        className="text-muted-foreground hover:text-destructive transition-colors p-2"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}

// ── Override field ─────────────────────────────────────────────────────────────

function OverrideField({
  field,
  value,
  onChange,
}: {
  field: OverrideableField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const [mode, setMode] = useState<"form" | "yaml">("form");
  const base =
    "w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow";

  const isArrayValue = Array.isArray(value);
  const isObjectValue = value !== null && typeof value === "object" && !isArrayValue;
  const effectiveType = isArrayValue ? "array" : isObjectValue ? "object" : field.type;

  if (effectiveType === "boolean") {
    return (
      <div className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20">
        <input
          type="checkbox"
          id={field.path}
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="h-5 w-5 rounded border-border text-primary cursor-pointer"
        />
        <label htmlFor={field.path} className="text-sm cursor-pointer select-none">
          {field.description || field.path}
        </label>
      </div>
    );
  }

  if (effectiveType === "integer") {
    return (
      <input
        type="number"
        className={base}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      />
    );
  }

  if (effectiveType === "array") {
    const arrValue = Array.isArray(value) ? value : [];
    const yamlStr = typeof value === "string" ? value : jsYaml.dump(arrValue, { indent: 2, lineWidth: 120 });

    const getEmptyItem = () => {
      if (arrValue.length > 0 && typeof arrValue[0] === "object" && arrValue[0] !== null) {
        const template: Record<string, unknown> = {};
        for (const key of Object.keys(arrValue[0] as Record<string, unknown>)) {
          const sample = (arrValue[0] as Record<string, unknown>)[key];
          if (typeof sample === "string") template[key] = "";
          else if (typeof sample === "number") template[key] = 0;
          else if (typeof sample === "boolean") template[key] = false;
          else if (Array.isArray(sample)) template[key] = [];
          else template[key] = "";
        }
        return template;
      }
      return "";
    };

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-1 p-0.5 rounded-lg bg-muted/50 w-fit">
          <button
            type="button"
            onClick={() => setMode("form")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
              mode === "form" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <List className="h-3.5 w-3.5" />
            Form
          </button>
          <button
            type="button"
            onClick={() => setMode("yaml")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
              mode === "yaml" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Code className="h-3.5 w-3.5" />
            YAML
          </button>
        </div>

        {mode === "form" ? (
          <div className="space-y-2">
            {arrValue.length === 0 ? (
              <div className="rounded-lg border-2 border-dashed p-4 text-center text-sm text-muted-foreground">
                No items yet
              </div>
            ) : (
              arrValue.map((item, idx) => (
                <ArrayItemEditor
                  key={idx}
                  item={item}
                  index={idx}
                  onUpdate={(newVal) => {
                    const newArr = [...arrValue];
                    newArr[idx] = newVal;
                    onChange(newArr);
                  }}
                  onRemove={() => {
                    const newArr = arrValue.filter((_, i) => i !== idx);
                    onChange(newArr);
                  }}
                />
              ))
            )}
            <button
              type="button"
              onClick={() => onChange([...arrValue, getEmptyItem()])}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "w-full")}
            >
              <Plus className="h-4 w-4 mr-1" />
              Add Item
            </button>
          </div>
        ) : (
          <textarea
            className="w-full rounded-lg border font-mono text-xs p-3 min-h-[150px] resize-y bg-zinc-950 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-primary/50"
            value={yamlStr}
            placeholder="# Enter array as YAML..."
            onChange={(e) => {
              try {
                const parsed = jsYaml.load(e.target.value);
                if (Array.isArray(parsed)) onChange(parsed);
                else onChange(e.target.value);
              } catch {
                onChange(e.target.value);
              }
            }}
          />
        )}
      </div>
    );
  }

  if (effectiveType === "object") {
    const objValue = (isObjectValue ? value : {}) as Record<string, unknown>;
    const yamlStr = typeof value === "string" ? value : jsYaml.dump(objValue, { indent: 2, lineWidth: 120 });

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-1 p-0.5 rounded-lg bg-muted/50 w-fit">
          <button
            type="button"
            onClick={() => setMode("form")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
              mode === "form" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <FileText className="h-3.5 w-3.5" />
            Form
          </button>
          <button
            type="button"
            onClick={() => setMode("yaml")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
              mode === "yaml" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Code className="h-3.5 w-3.5" />
            YAML
          </button>
        </div>

        {mode === "form" ? (
          <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
            {Object.keys(objValue).length === 0 ? (
              <div className="text-center text-sm text-muted-foreground py-2">No properties</div>
            ) : (
              Object.entries(objValue).map(([key, val]) => (
                <div key={key} className="flex items-center gap-3">
                  <label className="text-xs font-medium text-muted-foreground w-32 shrink-0 truncate">{key}</label>
                  {typeof val === "boolean" ? (
                    <input
                      type="checkbox"
                      checked={val}
                      onChange={(e) => onChange({ ...objValue, [key]: e.target.checked })}
                      className="h-4 w-4 rounded border-border text-primary"
                    />
                  ) : Array.isArray(val) ? (
                    <input
                      type="text"
                      className="flex-1 rounded border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                      value={val.join(", ")}
                      onChange={(e) => onChange({ ...objValue, [key]: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })}
                      placeholder="comma-separated"
                    />
                  ) : typeof val === "object" && val !== null ? (
                    <span className="text-xs text-muted-foreground italic">nested object (use YAML)</span>
                  ) : (
                    <input
                      type={typeof val === "number" ? "number" : "text"}
                      className="flex-1 rounded border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                      value={String(val ?? "")}
                      onChange={(e) => onChange({ ...objValue, [key]: typeof val === "number" ? Number(e.target.value) : e.target.value })}
                    />
                  )}
                </div>
              ))
            )}
          </div>
        ) : (
          <textarea
            className="w-full rounded-lg border font-mono text-xs p-3 min-h-[150px] resize-y bg-zinc-950 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-primary/50"
            value={yamlStr}
            placeholder="# Enter object as YAML..."
            onChange={(e) => {
              try {
                const parsed = jsYaml.load(e.target.value);
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) onChange(parsed);
                else onChange(e.target.value);
              } catch {
                onChange(e.target.value);
              }
            }}
          />
        )}
      </div>
    );
  }

  return (
    <input
      type="text"
      className={base}
      value={String(value ?? "")}
      placeholder={field.description || field.path}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NewClusterPage() {
  const isAdmin = useIsAdmin();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<"spec" | "vars">("spec");
  const [selectedSpec, setSelectedSpec] = useState<ClusterSpec | null>(null);
  const [clusterName, setClusterName] = useState("");
  const [site, setSite] = useState("");
  const [newSiteName, setNewSiteName] = useState("");
  const [mce, setMce] = useState("");
  const [newMceName, setNewMceName] = useState("");
  const [variables, setVariables] = useState<Record<string, unknown>>({});
  const [addonOverrides, setAddonOverrides] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [reviewOpen, setReviewOpen] = useState(false);

  const { data: specs, isLoading } = useQuery<ClusterSpec[]>({
    queryKey: ["specs"],
    queryFn: () => api.get<ClusterSpec[]>("/api/day1/specs"),
    staleTime: 60_000,
  });

  const { data: sites = [], isLoading: sitesLoading } = useQuery<string[]>({
    queryKey: ["sites"],
    queryFn: () => api.get<string[]>("/api/day1/sites"),
    staleTime: 60_000,
  });

  const { data: mces = [], isLoading: mcesLoading } = useQuery<string[]>({
    queryKey: ["sites", site, "mces"],
    queryFn: () => api.get<string[]>(`/api/day1/sites/${site}/mces`),
    enabled: Boolean(site) && site !== CREATE_NEW,
    staleTime: 60_000,
  });

  const createSiteMutation = useMutation({
    mutationFn: (name: string) => api.post<MRDetail>("/api/day1/sites", { name }),
    onSuccess: (mr) => {
      toast.success(`Site MR #${mr.iid} created. Site will be available after merge.`);
      queryClient.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: (err: Error) => toast.error(`Failed to create site: ${err.message}`),
  });

  const createMceMutation = useMutation({
    mutationFn: ({ siteName, mceName }: { siteName: string; mceName: string }) =>
      api.post<MRDetail>(`/api/day1/sites/${siteName}/mces`, { name: mceName }),
    onSuccess: (mr) => {
      toast.success(`MCE MR #${mr.iid} created. MCE will be available after merge.`);
      queryClient.invalidateQueries({ queryKey: ["sites", site, "mces"] });
    },
    onError: (err: Error) => toast.error(`Failed to create MCE: ${err.message}`),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<MRDetail>("/api/day1/clusters", {
        name: clusterName.trim(),
        site: site === CREATE_NEW ? newSiteName.trim() : site.trim(),
        mce: mce === CREATE_NEW ? newMceName.trim() : mce.trim(),
        spec_name: selectedSpec!.metadata.name,
        spec_version: selectedSpec!.metadata.version,
        variables,
        addon_overrides: addonOverrides,
      }),
    onSuccess: (mr) => {
      toast.success(`MR #${mr.iid} created: ${mr.title}`);
      setReviewOpen(false);
      router.push("/clusters");
    },
    onError: (err: Error) => {
      toast.error(`Failed: ${err.message}`);
      setReviewOpen(false);
    },
  });

  const effectiveSite = site === CREATE_NEW ? newSiteName.trim() : site.trim();
  const effectiveMce = mce === CREATE_NEW ? newMceName.trim() : mce.trim();

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3 text-center">
        <p className="text-lg font-semibold">Insufficient permissions</p>
        <p className="text-sm text-muted-foreground">Your role (viewer) does not have access to create clusters.</p>
        <Link href="/clusters" className={buttonVariants({ variant: "outline", size: "sm" })}>Back to clusters</Link>
      </div>
    );
  }

  const handleSelectSpec = (spec: ClusterSpec) => {
    setSelectedSpec(spec);
    const defaults: Record<string, unknown> = {};
    for (const v of spec.spec.day1.variables) {
      if (v.default !== undefined) defaults[v.name] = v.default;
    }
    setVariables(defaults);

    // Initialize addon overrides with default values
    const overrides: Record<string, Record<string, unknown>> = {};
    for (const addon of spec.spec.day2.addons) {
      const addonKey = `${addon.team}/${addon.name}`;
      if (addon.overrideable && addon.overrideable.length > 0) {
        overrides[addonKey] = {};
        for (const field of addon.overrideable) {
          if (field.default !== undefined) {
            overrides[addonKey][field.path] = field.default;
          }
        }
      }
    }
    setAddonOverrides(overrides);
    setStep("vars");
  };

  const handleReview = () => {
    if (!clusterName.trim()) { toast.error("Cluster name is required"); return; }
    if (!effectiveSite) { toast.error("Site is required"); return; }
    if (!effectiveMce) { toast.error("MCE is required"); return; }
    for (const v of selectedSpec!.spec.day1.variables) {
      if (v.required && !variables[v.name] && variables[v.name] !== 0 && variables[v.name] !== false) {
        toast.error(`Variable "${v.name}" is required`);
        return;
      }
    }
    setReviewOpen(true);
  };

  const handleSiteChange = (value: string | null) => {
    setSite(value ?? "");
    setMce("");
    setNewMceName("");
  };

  const handleMceChange = (value: string | null) => {
    setMce(value ?? "");
  };

  return (
    <div className="p-6 lg:p-8 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href="/clusters" className={buttonVariants({ variant: "ghost", size: "icon" })}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            New Cluster
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {step === "spec" ? "Step 1 of 2 — Choose a spec" : `Step 2 of 2 — Configure "${selectedSpec?.metadata.name}"`}
          </p>
        </div>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 text-sm">
        <span className={cn("flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold",
          step === "spec" ? "bg-primary text-white" : "bg-[#00c875] text-white")}>
          {step === "spec" ? "1" : <CheckCircle2 className="h-4 w-4" />}
        </span>
        <span className={step === "spec" ? "font-semibold" : "text-muted-foreground"}>Choose Spec</span>
        <div className="h-px w-8 bg-border" />
        <span className={cn("flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold",
          step === "vars" ? "bg-primary text-white" : "bg-muted text-muted-foreground")}>
          2
        </span>
        <span className={step === "vars" ? "font-semibold" : "text-muted-foreground"}>Configure</span>
      </div>

      {/* Step 1: Select spec */}
      {step === "spec" && (
        <div className="space-y-3">
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
          ) : specs?.length === 0 ? (
            <div className="bg-card rounded-xl border p-8 text-center text-muted-foreground">
              No specs available.{" "}
              <Link href="/specs/new" className="text-primary hover:underline">Create a spec first</Link>.
            </div>
          ) : (
            specs?.map((spec) => (
              <button
                key={spec.metadata.name}
                onClick={() => handleSelectSpec(spec)}
                className="w-full text-left bg-card rounded-xl border shadow-sm hover:border-primary/50 hover:shadow-md transition-all p-5 group"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold group-hover:text-primary transition-colors">
                      {spec.metadata.name}
                    </h3>
                    {spec.metadata.description && (
                      <p className="text-sm text-muted-foreground mt-0.5">{spec.metadata.description}</p>
                    )}
                    <p className="text-xs text-muted-foreground mt-1.5">
                      {spec.spec.day1.variables.length} variables · {spec.spec.day2.addons.length} addons
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="rounded-full px-2 py-0.5 text-xs bg-primary/8 text-primary font-medium">
                      v{spec.metadata.version}
                    </span>
                    <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      )}

      {/* Step 2: Fill variables */}
      {step === "vars" && selectedSpec && (
        <div className="space-y-6">
          {/* Cluster identity */}
          <div className="bg-card rounded-xl border shadow-sm p-5 space-y-4">
            <h2 className="text-sm font-semibold">Cluster Identity</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Cluster Name <span className="text-destructive">*</span>
                </label>
                <input
                  type="text"
                  className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
                  placeholder="e.g. alpha-prod"
                  value={clusterName}
                  onChange={(e) => setClusterName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  Site <span className="text-destructive">*</span>
                </label>
                <Select value={site} onValueChange={handleSiteChange} disabled={sitesLoading}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select site…" />
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {sites.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                    {sites.length > 0 && <SelectSeparator />}
                    <SelectItem value={CREATE_NEW}>
                      <Plus className="h-3.5 w-3.5 mr-1" />
                      Create new site
                    </SelectItem>
                  </SelectContent>
                </Select>
                {site === CREATE_NEW && (
                  <div className="flex gap-2 mt-2">
                    <input
                      type="text"
                      className="flex-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
                      placeholder="New site name"
                      value={newSiteName}
                      onChange={(e) => setNewSiteName(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => newSiteName.trim() && createSiteMutation.mutate(newSiteName.trim())}
                      disabled={!newSiteName.trim() || createSiteMutation.isPending}
                      className={cn(buttonVariants({ variant: "outline", size: "sm" }), "shrink-0")}
                    >
                      <Plus className="h-4 w-4 mr-1" />Create
                    </button>
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  MCE <span className="text-destructive">*</span>
                </label>
                <Select
                  value={mce}
                  onValueChange={handleMceChange}
                  disabled={!site || site === CREATE_NEW || mcesLoading}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={!site ? "Select site first…" : "Select MCE…"} />
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {mces.map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                    {site && site !== CREATE_NEW && (
                      <>
                        {mces.length > 0 && <SelectSeparator />}
                        <SelectItem value={CREATE_NEW}>
                          <Plus className="h-3.5 w-3.5 mr-1" />
                          Create new MCE
                        </SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
                {mce === CREATE_NEW && site && site !== CREATE_NEW && (
                  <div className="flex gap-2 mt-2">
                    <input
                      type="text"
                      className="flex-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow"
                      placeholder="New MCE name"
                      value={newMceName}
                      onChange={(e) => setNewMceName(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => newMceName.trim() && createMceMutation.mutate({ siteName: site, mceName: newMceName.trim() })}
                      disabled={!newMceName.trim() || createMceMutation.isPending}
                      className={cn(buttonVariants({ variant: "outline", size: "sm" }), "shrink-0")}
                    >
                      <Plus className="h-4 w-4 mr-1" />Create
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Spec variables (excluding identity fields already captured above) */}
          {selectedSpec.spec.day1.variables.filter((v) => !IDENTITY_VARIABLES.has(v.name)).length > 0 && (
            <div className="bg-card rounded-xl border shadow-sm p-5 space-y-4">
              <h2 className="text-sm font-semibold">Spec Variables</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                {selectedSpec.spec.day1.variables.filter((v) => !IDENTITY_VARIABLES.has(v.name)).map((v) => (
                  <div key={v.name} className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      {formatVariableName(v.name)}
                      {v.required && <span className="text-destructive ml-0.5">*</span>}
                    </label>
                    <VariableField
                      variable={v}
                      value={variables[v.name] ?? ""}
                      onChange={(val) => setVariables((prev) => ({ ...prev, [v.name]: val }))}
                    />
                    {v.description && (
                      <p className="text-xs text-muted-foreground">{v.description}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Addons and overrides */}
          {selectedSpec.spec.day2.addons.length > 0 && (
            <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b bg-muted/30">
                <h2 className="text-sm font-semibold">Addon Configuration</h2>
                <p className="text-xs text-muted-foreground mt-0.5">Customize addon values for this cluster</p>
              </div>
              <div className="p-5 space-y-4">
                {selectedSpec.spec.day2.addons.map((addon) => {
                  const addonKey = `${addon.team}/${addon.name}`;
                  const hasOverrides = addon.overrideable && addon.overrideable.length > 0;
                  const simpleFields = addon.overrideable?.filter(f => f.type !== "array" && f.type !== "object" && !Array.isArray(addonOverrides[addonKey]?.[f.path] ?? f.default)) ?? [];
                  const complexFields = addon.overrideable?.filter(f => f.type === "array" || f.type === "object" || Array.isArray(addonOverrides[addonKey]?.[f.path] ?? f.default)) ?? [];

                  return (
                    <div
                      key={addonKey}
                      className="rounded-xl border bg-background overflow-hidden"
                    >
                      <div className="flex items-center justify-between px-4 py-3 bg-muted/20 border-b">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
                            <span className="text-xs font-bold text-primary">{addon.name.charAt(0).toUpperCase()}</span>
                          </div>
                          <div>
                            <span className="font-semibold text-sm">{addon.name}</span>
                            <span className="ml-2 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary font-medium">
                              {addon.version}
                            </span>
                          </div>
                        </div>
                        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">{addon.team}</span>
                      </div>

                      {hasOverrides ? (
                        <div className="p-4 space-y-4">
                          {simpleFields.length > 0 && (
                            <div className="grid gap-4 sm:grid-cols-2">
                              {simpleFields.map((field) => (
                                <div key={field.path} className="space-y-1.5">
                                  <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                    {field.path}
                                  </label>
                                  <OverrideField
                                    field={field}
                                    value={addonOverrides[addonKey]?.[field.path] ?? field.default ?? ""}
                                    onChange={(val) =>
                                      setAddonOverrides((prev) => ({
                                        ...prev,
                                        [addonKey]: {
                                          ...prev[addonKey],
                                          [field.path]: val,
                                        },
                                      }))
                                    }
                                  />
                                  {field.description && (
                                    <p className="text-xs text-muted-foreground">{field.description}</p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}

                          {complexFields.length > 0 && (
                            <div className="space-y-4">
                              {simpleFields.length > 0 && <div className="border-t" />}
                              {complexFields.map((field) => (
                                <div key={field.path} className="space-y-2">
                                  <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                    {field.path}
                                  </label>
                                  <OverrideField
                                    field={field}
                                    value={addonOverrides[addonKey]?.[field.path] ?? field.default ?? ""}
                                    onChange={(val) =>
                                      setAddonOverrides((prev) => ({
                                        ...prev,
                                        [addonKey]: {
                                          ...prev[addonKey],
                                          [field.path]: val,
                                        },
                                      }))
                                    }
                                  />
                                  {field.description && (
                                    <p className="text-xs text-muted-foreground">{field.description}</p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="px-4 py-3 text-xs text-muted-foreground italic">
                          No configurable fields for this addon
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <button onClick={() => setStep("spec")} className={buttonVariants({ variant: "outline" })}>
              <ArrowLeft className="h-4 w-4 mr-1.5" />Back
            </button>
            <button
              onClick={handleReview}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
            >
              <Eye className="h-4 w-4" />
              Review & Create
            </button>
          </div>
        </div>
      )}

      {/* Review dialog */}
      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        title="Review: Create Cluster"
        description="Review the cluster configuration below. Confirming will create a GitLab MR for approval."
        onConfirm={() => createMutation.mutate()}
        isPending={createMutation.isPending}
        confirmLabel="Confirm — Create Cluster MR"
      >
        <div className="rounded-lg border bg-muted/30 p-4 space-y-3 text-sm font-mono">
          {/* Identity */}
          <div className="space-y-1">
            <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide mb-2">Identity</p>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">cluster_name</span>
              <span className="font-medium">{clusterName}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">site</span>
              <span className="font-medium">{effectiveSite}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">mce</span>
              <span className="font-medium">{effectiveMce}</span>
            </div>
          </div>

          {/* Spec */}
          <div className="border-t pt-3 space-y-1">
            <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide mb-2">Spec</p>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">name</span>
              <span className="font-medium">{selectedSpec?.metadata.name}</span>
            </div>
            <div className="flex gap-3">
              <span className="text-muted-foreground w-28 shrink-0">version</span>
              <span className="font-medium">v{selectedSpec?.metadata.version}</span>
            </div>
          </div>

          {/* Variables */}
          {Object.keys(variables).length > 0 && (
            <div className="border-t pt-3 space-y-1">
              <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide mb-2">Variables</p>
              {Object.entries(variables).map(([k, v]) => (
                <div key={k} className="flex gap-3">
                  <span className="text-muted-foreground w-28 shrink-0 truncate">{k}</span>
                  <span className="font-medium">{String(v ?? "—")}</span>
                </div>
              ))}
            </div>
          )}

          {/* Addons */}
          {selectedSpec && selectedSpec.spec.day2.addons.length > 0 && (
            <div className="border-t pt-3">
              <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Addons ({selectedSpec.spec.day2.addons.length})
              </p>
              <div className="space-y-2">
                {selectedSpec.spec.day2.addons.map((addon) => {
                  const addonKey = `${addon.team}/${addon.name}`;
                  const overrides = addonOverrides[addonKey] ?? {};
                  const hasOverrides = Object.keys(overrides).length > 0;
                  return (
                    <div key={addonKey}>
                      <div className="flex gap-3">
                        <span className="text-muted-foreground w-28 shrink-0 truncate">{addon.name}</span>
                        <span className="font-medium">v{addon.version} · {addon.team}</span>
                      </div>
                      {hasOverrides && (
                        <div className="ml-28 mt-1 pl-3 border-l-2 border-primary/20 space-y-0.5">
                          {Object.entries(overrides).map(([path, value]) => (
                            <div key={path} className="flex gap-2 text-xs">
                              <span className="text-primary/70">{path}:</span>
                              <span className="font-medium">{String(value)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </ReviewDialog>
    </div>
  );
}
