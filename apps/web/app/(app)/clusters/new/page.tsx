"use client";

import { useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Code, Eye, FileText, Info, List, Plus, RotateCcw, Sparkles, Trash2,
} from "lucide-react";
import jsYaml from "js-yaml";
import { toast } from "sonner";
import { api, isApiError } from "@/lib/api-client";
import { approvalHref } from "@/lib/approvals";
import { day2Api, day2Keys } from "@/lib/day2";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { writeErrorTitle } from "@/lib/write-errors";
import { buttonVariants } from "@/components/ui/button";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { ReviewDialog } from "@/components/common/review-dialog";
import { GitLabFileList } from "@/components/common/gitlab-file-list";
import { ProblemList } from "@/components/common/problem-list";
import { EmptyState, EmptyStateLink } from "@/components/common/empty-state";
import { getValueAtPath } from "@/components/specs/configure-overrideable-dialog";
import { useIsAdmin } from "@/stores/auth-store";
import type {
  CatalogEntry, ClusterPreview, CreateClusterRequest, MRDetail, Mce, NameSuggestion, OpenShiftVersions, OverrideableField,
  ProvisionRun, SpecEntry, TemplateField,
} from "@/types";
import { ProvisionRunPanel } from "@/components/clusters/provision-run";
import { MCEPlacementPanel } from "@/components/clusters/mce-placement";
import { isProvisionRun, useProvisioner } from "@/lib/provision";
import {
  PLACEMENT_ENVS, REASON_MAX, changedPick, cleanReason, placementNeeds, placementOwner, useDebounced, usePlacement,
  type PlacementEnv,
} from "@/lib/placement";
import {
  DynamicVariableForm, FlavorBadge, fieldInputClassName, type FieldInputContext, type FieldValue, type FormValues,
} from "@/components/clusters/dynamic-variable-form";
import { ConfigListEditor } from "@/components/machine-configs/config-list-editor";
import { asEntries, NETWORK_CONFIG, useMachineConfigs } from "@/lib/machine-configs";
import {
  CONFIGS, NODEPOOLS, fieldPaths, flavorLocks, flavorProblems, formEntries, isConfigsPath, lookup, newNodepool,
  nodepoolConfigsPath, ownerProblems, OWNER_INPUTS, placeProblems, presetPaths, requestVariables, seedCreateForm,
  sizedIndex, sizingRatio, startingSize, withSize, type PlacedProblems,
} from "./flavor-form";

const inputCls =
  "w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-shadow";

function formatVariableName(name: string) {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Naming convention (ADR-0014), mirrored from day1's domain/names.py ────────
//
// The server is authoritative; this only gives the hint while typing.

const DNS_LABEL = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;
const MAX_DNS_LABEL = 63;

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** `ocp4-<env>-<name>-<site>[-<seq>]` for one site; group 1 is the env. */
function clusterNamePattern(site: string) {
  return new RegExp(
    `^ocp4-(prod|prep|test)-([a-z0-9](?:[-a-z0-9]*[a-z0-9])?)-${escapeRegExp(site)}(?:-([a-z0-9]+))?$`
  );
}

/** Why the server would refuse `name` under `site` and `mce`; `siteMces` once they have loaded. */
function nameProblems(name: string, site: string, mce: Mce | undefined, siteMces: Mce[] | undefined): string[] {
  const problems: string[] = [];
  if (name.length > MAX_DNS_LABEL) problems.push(`Longer than ${MAX_DNS_LABEL} characters`);
  if (!DNS_LABEL.test(name)) {
    problems.push("Use lowercase letters, digits and '-', starting and ending with a letter or digit");
  }
  if (!site) return problems;
  const match = clusterNamePattern(site).exec(name);
  if (match?.[3] !== undefined && !/^[a-z]$/.test(match[3])) {
    problems.push(`The sequence "${match[3]}" must be one letter, a to z (-a, -b, …): a number is not the convention`);
  }
  if (!match) {
    problems.push(`Does not follow ocp4-<env>-<name>-${site}[-<letter>]`);
  } else if (mce) {
    if (mce.follows_convention && mce.env && match[1] !== mce.env) {
      problems.push(`Env "${match[1]}" does not match ${mce.name} (env "${mce.env}")`);
    }
  } else if (siteMces && !siteMces.some((m) => m.follows_convention && m.env === match[1])) {
    problems.push(`No "${match[1]}" MCE on ${site} follows the convention, so this env cannot be created there`);
  }
  return problems;
}

/** The site whose convention the name follows; the longest wins (`site-a` over `site`). */
function siteFromName(name: string, sites: string[]): string | null {
  const matches = sites.filter((s) => clusterNamePattern(s).test(name));
  return matches.sort((a, b) => b.length - a.length)[0] ?? null;
}

/** An MCE to choose: what it hosts under; one off the convention is listed apart and cannot be chosen. */
function mceOption(mce: Mce): ComboboxOption {
  if (!mce.follows_convention) {
    return {
      value: mce.name,
      label: mce.name,
      description: `Does not follow ocp4-<env>-mce-${mce.site}-<letter>`,
      group: "Off convention",
      disabled: true,
    };
  }
  const facts = [
    mce.env && `env ${mce.env}`,
    mce.default_mastertag && `OCP ${mce.default_mastertag}`,
    `${mce.cluster_count} cluster${mce.cluster_count === 1 ? "" : "s"}`,
  ];
  return { value: mce.name, label: mce.name, description: facts.filter(Boolean).join(" · ") };
}

const asOption = (value: string): ComboboxOption => ({ value, label: value });

/** The entry of `offered` that `version` names (`4.18.56-x86_64` is `4.18.56`), or `null`. */
function offeredRelease(version: unknown, offered: string[]): string | null {
  if (typeof version !== "string" || !version.trim()) return null;
  const bare = version.trim().replace(/-x86_64$/, "");
  return offered.includes(bare) ? bare : null;
}

/** The env a name following the site's convention carries, when a cluster can be placed in it (prod or prep). */
function envFromName(name: string, site: string): PlacementEnv | null {
  const env = clusterNamePattern(site).exec(name)?.[1];
  return PLACEMENT_ENVS.find((e) => e === env) ?? null;
}

/** The owner input placement ranks by (ADR-0028, decision 6). */
const OWNER_MADOR = "owner_mador";
/** How long the owner must stay as typed before placement is asked again. */
const OWNER_DEBOUNCE_MS = 400;

/** The one conventional MCE of the site whose env the name carries. */
function mceFromName(name: string, site: string, mces: Mce[]): string | null {
  const env = clusterNamePattern(site).exec(name)?.[1];
  if (!env) return null;
  const candidates = mces.filter((m) => m.follows_convention && m.env === env);
  return candidates.length === 1 ? candidates[0].name : null;
}

// ── Form values ──────────────────────────────────────────────────────────────

function isEmptyValue(value: unknown): boolean {
  if (value === undefined || value === null || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

/**
 * Every required input left empty, at any depth (`nodepools[1].infra_env`).
 * Not a locked value (the flavor's, which the person cannot change) nor a
 * config list's entries (the picker checks those, `flavorProblems`).
 */
function missingRequired(
  schema: TemplateField[], values: Record<string, unknown>, locked: ReadonlyMap<string, unknown>, prefix = ""
): string[] {
  const missing: string[] = [];
  for (const field of schema) {
    const path = prefix ? `${prefix}.${field.name}` : field.name;
    const value = values[field.name];
    if (locked.has(path) || isConfigsPath(path)) continue;
    if (field.type === "list" && field.fields?.length) {
      const items = Array.isArray(value) ? value : [];
      if (field.required && items.length === 0) missing.push(path);
      items.forEach((item, i) => {
        if (item && typeof item === "object") {
          missing.push(...missingRequired(field.fields!, item as Record<string, unknown>, locked, `${path}[${i}]`));
        }
      });
    } else if (field.required && isEmptyValue(value)) {
      missing.push(path);
    }
  }
  return missing;
}

/** `nodepools[1].configs[0].name` → `Nodepool 2 › Config 1 › Name`. */
function labelForPath(path: string): string {
  return path
    .split(".")
    .map((part) => {
      const item = /^(\w+)\[(\d+)\]$/.exec(part);
      return item
        ? `${formatVariableName(item[1]).replace(/s$/, "")} ${Number(item[2]) + 1}`
        : formatVariableName(part);
    })
    .join(" › ");
}

function setValueAtPath(obj: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const [head, ...rest] = path.split(".");
  if (rest.length === 0) return { ...obj, [head]: value };
  const child = obj[head];
  const base = child && typeof child === "object" && !Array.isArray(child) ? (child as Record<string, unknown>) : {};
  return { ...obj, [head]: setValueAtPath(base, rest.join("."), value) };
}

/** Drop the leaves a form field left blank, and the maps that leaves empty. */
function pruneEmpty(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value === "" || value === undefined) continue;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const nested = pruneEmpty(value as Record<string, unknown>);
      if (Object.keys(nested).length > 0) out[key] = nested;
    } else {
      out[key] = value;
    }
  }
  return out;
}

/** Override defaults the spec declares, as nested Helm values. */
function defaultOverrides(fields: OverrideableField[]): Record<string, unknown> {
  let values: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.default !== undefined && field.default !== null) values = setValueAtPath(values, field.path, field.default);
  }
  return values;
}

/** The chart's clusterName for the file name of a network config: the default `ocp4-` stripped (ADR-0015). */
function chartClusterName(name: string): string {
  return name.replace(/^ocp4-/, "");
}

/** An owner number (ADR-0028): text, typed on a numeric keypad, sent as the text. */
function OwnerInput({ field, value, onChange, invalid }: {
  field: TemplateField; value: FieldValue; onChange: (v: FieldValue) => void; invalid: boolean;
}) {
  return (
    <input
      type="text"
      inputMode="numeric"
      autoComplete="off"
      spellCheck={false}
      data-testid={`owner-input-${field.name}`}
      className={cn(fieldInputClassName, "font-mono", invalid && "border-destructive focus:ring-destructive/20")}
      value={value === undefined || value === null ? "" : String(value)}
      placeholder={field.example ? `e.g. ${field.example}` : "digits, like 1234"}
      aria-label={formatVariableName(field.name)}
      aria-invalid={invalid}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function summarizeValue(value: unknown): string {
  if (Array.isArray(value)) return `${value.length} item${value.length !== 1 ? "s" : ""}`;
  if (value && typeof value === "object") return "configured";
  return value === "" || value === undefined || value === null ? "—" : String(value);
}

// ── Array item editor ──────────────────────────────────────────────────────────

function ArrayItemEditor({
  item,
  index,
  onUpdate,
  onRemove,
}: {
  item: unknown;
  index: number;
  onUpdate: (v: unknown) => void;
  onRemove: () => void;
}) {
  const isObject = item !== null && typeof item === "object" && !Array.isArray(item);

  if (isObject) {
    const obj = item as Record<string, unknown>;
    return (
      <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">Item {index + 1}</span>
          <button type="button" onClick={onRemove} aria-label={`Remove item ${index + 1}`} className="text-muted-foreground hover:text-destructive transition-colors">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
        {Object.entries(obj).map(([key, val]) => (
          <div key={key} className="flex items-center gap-3">
            <label className="text-xs font-medium text-muted-foreground w-32 shrink-0 truncate">{key}</label>
            <input
              type={typeof val === "number" ? "number" : "text"}
              className="flex-1 min-w-0 rounded border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
              value={String(val ?? "")}
              onChange={(e) =>
                onUpdate({ ...obj, [key]: typeof val === "number" ? Number(e.target.value) : e.target.value })
              }
            />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        className="flex-1 min-w-0 rounded border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
        value={String(item ?? "")}
        onChange={(e) => onUpdate(e.target.value)}
      />
      <button type="button" onClick={onRemove} aria-label={`Remove item ${index + 1}`} className="text-muted-foreground hover:text-destructive transition-colors">
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// ── Override field ─────────────────────────────────────────────────────────────

function ModeToggle({ mode, onChange, formIcon: FormIcon }: {
  mode: "form" | "yaml"; onChange: (m: "form" | "yaml") => void; formIcon: typeof List;
}) {
  return (
    <div className="flex items-center gap-1 p-0.5 rounded-lg bg-muted/50 w-fit">
      {([["form", FormIcon, "Form"], ["yaml", Code, "YAML"]] as const).map(([value, Icon, label]) => (
        <button
          key={value}
          type="button"
          onClick={() => onChange(value)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
            mode === value ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </div>
  );
}

function OverrideField({
  id,
  field,
  value,
  onChange,
}: {
  id: string;
  field: OverrideableField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const [mode, setMode] = useState<"form" | "yaml">("form");

  const isArrayValue = Array.isArray(value);
  const isObjectValue = value !== null && typeof value === "object" && !isArrayValue;
  const effectiveType = isArrayValue ? "array" : isObjectValue ? "object" : field.type;

  if (effectiveType === "boolean") {
    return (
      <div className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20">
        <input
          type="checkbox"
          id={id}
          data-testid={id}
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="h-5 w-5 rounded border-border text-primary cursor-pointer"
        />
        <label htmlFor={id} className="text-sm cursor-pointer select-none">
          {field.description || field.path}
        </label>
      </div>
    );
  }

  if (effectiveType === "integer") {
    return (
      <input
        type="number"
        id={id}
        data-testid={id}
        className={inputCls}
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
      <div className="space-y-3" data-testid={id}>
        <ModeToggle mode={mode} onChange={setMode} formIcon={List} />
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
                  onRemove={() => onChange(arrValue.filter((_, i) => i !== idx))}
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
                onChange(Array.isArray(parsed) ? parsed : e.target.value);
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
      <div className="space-y-3" data-testid={id}>
        <ModeToggle mode={mode} onChange={setMode} formIcon={FileText} />
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
                      className="flex-1 min-w-0 rounded border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                      value={val.join(", ")}
                      onChange={(e) => onChange({ ...objValue, [key]: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                      placeholder="comma-separated"
                    />
                  ) : typeof val === "object" && val !== null ? (
                    <span className="text-xs text-muted-foreground italic">nested object (use YAML)</span>
                  ) : (
                    <input
                      type={typeof val === "number" ? "number" : "text"}
                      className="flex-1 min-w-0 rounded border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
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
                onChange(parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : e.target.value);
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
      id={id}
      data-testid={id}
      className={inputCls}
      value={String(value ?? "")}
      placeholder={field.description || field.path}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// ── Inline form errors ─────────────────────────────────────────────────────────

/** A failed preview or create (the service's problem), or the form's own check. */
type FormError =
  | {
      kind: "server";
      error: unknown;
      title: string;
      hint?: string;
      /** The spec changed under the form: offer to start again from the current one. */
      reloadSpec?: boolean;
      /** Day1's problems that are about a field of the form, shown there; the rest is listed here. */
      placed?: PlacedProblems & { values: FormValues };
    }
  | { kind: "form"; lines: string[] };

/**
 * Day1's 422 problems, each at the field its path names (§2 of the API note),
 * with the form's values they were about: a field shows them only until it
 * changes. `null` when none is about a field.
 */
function placeFailure(error: unknown, schema: TemplateField[], values: FormValues): (PlacedProblems & { values: FormValues }) | null {
  if (!isApiError(error, "VALIDATION_ERROR") || error.problems.length === 0) return null;
  const placed = placeProblems(error.problems, fieldPaths(schema, values));
  if (placed.placed === 0) return null;
  // FastAPI's field errors follow the problems in `messages()`; nothing of the form is about them
  const others = error.fieldErrors.length > 0 ? error.messages().slice(error.problems.length) : [];
  return { ...placed, rest: [...placed.rest, ...others], values };
}

function describeFailure(error: unknown, what: "preview" | "create"): FormError {
  const verb = what === "preview" ? "The cluster file could not be rendered" : "The merge request was not opened";
  if (isApiError(error, "ALREADY_EXISTS")) {
    return {
      kind: "server",
      error,
      title: "This cluster name is taken",
      hint: "A cluster with this name exists, or an open MR already creates it. Pick another name.",
    };
  }
  // The MCEs' numbers moved since the form showed them, so day1 now picks another (ADR-0050)
  const newPick = changedPick(error);
  if (newPick) {
    return {
      kind: "server",
      error,
      title: "Wingman's pick changed",
      hint: `Wingman now picks ${newPick}: the MCEs' numbers changed since the form showed them. Check the MCE above, then review again.`,
    };
  }
  if (isApiError(error, "REVISION_CONFLICT")) {
    return {
      kind: "server",
      error,
      title: "The flavor changed since you opened it",
      hint: "Reload the flavors and fill the form again from the current version.",
      reloadSpec: true,
    };
  }
  if (isApiError(error, "VALIDATION_ERROR")) return { kind: "server", error, title: `${verb}: fix the following` };
  if (isApiError(error, "NOT_FOUND")) {
    return { kind: "server", error, title: verb, hint: "The site, MCE or flavor no longer exists in GitLab. Reload the page." };
  }
  return { kind: "server", error, title: writeErrorTitle(error, verb) };
}

// ── Page ──────────────────────────────────────────────────────────────────────

type OverrideMode = "fields" | "yaml";

export default function NewClusterPage() {
  const isAdmin = useIsAdmin();
  const router = useRouter();
  const queryClient = useQueryClient();
  const errorRef = useRef<HTMLDivElement>(null);
  // The visible labels name the site, MCE and version controls
  const siteLabelId = useId();
  const mceLabelId = useId();
  const envLabelId = useId();
  const versionLabelId = useId();

  const [step, setStep] = useState<"spec" | "vars">("spec");
  const [selectedSpec, setSelectedSpec] = useState<SpecEntry | null>(null);
  const [clusterName, setClusterName] = useState("");
  // Until the person types a name, the form shows day1's suggestion (ADR-0040)
  const [nameEdited, setNameEdited] = useState(false);
  // `null` = untouched: the flavor's preset size, else 1
  const [sizeInput, setSizeInput] = useState<string | null>(null);
  // `null` = not chosen: the value is detected from the cluster name.
  const [siteChoice, setSiteChoice] = useState<string | null>(null);
  const [mceChoice, setMceChoice] = useState<string | null>(null);
  // With MCE placement (ADR-0050): `null` = not chosen, the env a typed name carries
  const [envChoice, setEnvChoice] = useState<PlacementEnv | null>(null);
  // An admin's other MCE than Wingman's pick, and why (decision 15); `null` = the pick
  const [mceOverride, setMceOverride] = useState<string | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [reasonMissing, setReasonMissing] = useState(false);
  // `null` = not chosen: the spec's preset, else the MCE's default mastertag, when the MCE offers it.
  const [ocpChoice, setOcpChoice] = useState<string | null>(null);
  // `null` = untouched: the form shows the spec's structure and presets.
  const [dynamicValues, setDynamicValues] = useState<FormValues | null>(null);
  // Nested Helm values per spec addon, keyed "team/name".
  const [addonOverrides, setAddonOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const [overrideModes, setOverrideModes] = useState<Record<string, OverrideMode>>({});
  const [addonYamlText, setAddonYamlText] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<FormError | null>(null);
  const [reviewed, setReviewed] = useState<{ request: CreateClusterRequest; preview: ClusterPreview } | null>(null);
  // The form's values when it was last sent: day1's problems are about these
  const submitted = useRef<FormValues | null>(null);

  const { data: specs, isLoading: specsLoading, error: specsError } = useQuery<SpecEntry[]>({
    queryKey: ["specs"],
    queryFn: () => api.get<SpecEntry[]>("/api/day1/specs"),
    staleTime: 60_000,
  });

  // Template schema — parsed server-side from the Jinja2 AST; drives the dynamic form
  const { data: templateSchema, isLoading: schemaLoading, error: schemaError } = useQuery<TemplateField[]>({
    queryKey: ["specs", "template-schema"],
    queryFn: () => api.get<TemplateField[]>("/api/day1/specs/template/schema"),
    staleTime: 300_000,
  });
  const schema = useMemo(() => templateSchema ?? [], [templateSchema]);

  // The day2 catalog: the team defaults seed the full values YAML editor
  const { data: addonCatalog = [] } = useQuery<CatalogEntry[]>({
    queryKey: day2Keys.catalog,
    queryFn: () => api.get<CatalogEntry[]>(day2Api.catalog),
    staleTime: 120_000,
    enabled: step === "vars",
  });

  const { data: sites = [], isLoading: sitesLoading, error: sitesError } = useQuery<string[]>({
    queryKey: ["sites"],
    queryFn: () => api.get<string[]>("/api/day1/sites"),
    staleTime: 60_000,
    enabled: step === "vars",
  });

  // The site and MCE a typed name follows; a suggested name follows the ones chosen
  const typedName = nameEdited ? clusterName.trim() : "";
  const detectedSite = typedName ? siteFromName(typedName, sites) : null;
  const site = siteChoice ?? detectedSite ?? "";

  const { data: mces = [], isLoading: mcesLoading, error: mcesError } = useQuery<Mce[]>({
    queryKey: ["mces", site],
    queryFn: () => api.get<Mce[]>(`/api/day1/mces?site=${encodeURIComponent(site)}`),
    enabled: Boolean(site),
    staleTime: 60_000,
  });

  // MCE placement (ADR-0050): Wingman picks the MCE from the site, prod or prep, the version and the
  // owner. Its first read, without a version, gives the versions the candidates host. It is `null`
  // (501) where this deployment does not read the MCEs: the form then keeps its MCE select.
  const detectedEnv = site && typedName ? envFromName(typedName, site) : null;
  const env = envChoice ?? detectedEnv ?? "";
  const flavorName = selectedSpec?.metadata.name;
  const versionsRead = usePlacement(step === "vars" && site ? { site, env: env || "prod", flavor: flavorName } : null);
  const placementMode = versionsRead.data != null || versionsRead.isError;
  const versionsFresh = placementMode && env !== "" && !versionsRead.isPlaceholderData && !versionsRead.isError;
  const placementVersions = versionsFresh ? (versionsRead.data?.versions ?? []) : [];

  // Without placement: the MCE chosen, or the one conventional MCE of the env a typed name carries
  const detectedMce = !placementMode && site && typedName ? mceFromName(typedName, site, mces) : null;
  const fallbackMce = mceChoice && mces.some((m) => m.name === mceChoice) ? mceChoice : (detectedMce ?? "");
  const fallbackSelected = mces.find((m) => m.name === fallbackMce);
  const offConventionMces = mces.filter((m) => !m.follows_convention);

  // The releases a new cluster on this MCE may use: the day1 repo's upgrade ladder in the
  // minors the MCE can host (ADR-0034). `problems` says why the list is short or empty.
  // With placement, the releases some candidate hosts (each candidate's version check says which).
  const { data: offered, isLoading: offeredLoading, error: offeredError } = useQuery<OpenShiftVersions>({
    queryKey: ["mce-openshift-versions", fallbackMce],
    queryFn: () => api.get<OpenShiftVersions>(`/api/day1/mces/${encodeURIComponent(fallbackMce)}/openshift-versions`),
    enabled: Boolean(fallbackMce) && step === "vars" && !placementMode,
    staleTime: 60_000,
  });
  const ocpVersions = placementMode ? placementVersions : (offered?.versions ?? []);
  const versionProblems = placementMode ? [] : (offered?.problems ?? []);
  const versionsLoading = placementMode
    ? env !== "" && (versionsRead.isLoading || versionsRead.isPlaceholderData)
    : offeredLoading;
  const versionsError = placementMode ? (env ? versionsRead.error : null) : offeredError;

  // A preset prefills only a release the MCE offers; one it can't host leaves the field empty.
  const presetVersion = selectedSpec?.spec.day1.values?.openshift_release_version;
  const hasPreset = typeof presetVersion === "string" && presetVersion.trim() !== "";
  const presetOffered = offeredRelease(presetVersion, ocpVersions);
  const mceDefaultOffered = placementMode ? null : offeredRelease(fallbackSelected?.default_mastertag, ocpVersions);
  const versionDefault = hasPreset
    ? presetOffered ? { value: presetOffered, source: `preset by spec ${selectedSpec?.metadata.name}` } : null
    : mceDefaultOffered && fallbackSelected
    ? { value: mceDefaultOffered, source: `default of ${fallbackSelected.name}` }
    : null;
  const presetNotOffered = hasPreset && (placementMode ? versionsFresh : offered !== undefined) && !presetOffered;
  // Typed when the list could not be read; otherwise a choice made for another MCE counts only if this one offers it.
  const chosenVersion = versionsError ? ocpChoice : ocpChoice !== null && ocpVersions.includes(ocpChoice) ? ocpChoice : null;
  const ocpVersion = chosenVersion ?? versionDefault?.value ?? "";
  const versionOptions = ocpVersions.map(asOption);
  const siteOptions = sites.map(asOption);
  const mceOptions = mces.map(mceOption);

  // What a nodepool's configs may name, and the defaults a new nodepool starts with (§1)
  const {
    data: catalog, isLoading: catalogLoading, error: catalogError,
  } = useMachineConfigs(step === "vars");
  const nodepoolsField = schema.find((f) => f.name === NODEPOOLS && f.type === "list" && f.fields?.length);
  const hasConfigs = Boolean(nodepoolsField?.fields?.some((f) => f.name === CONFIGS && f.type === "list"));

  // The flavor's locks, presets and starting nodepools (ADR-0026 to ADR-0029)
  const locks = useMemo(
    () => (selectedSpec ? flavorLocks(selectedSpec) : { values: new Map<string, unknown>(), rule: null }),
    [selectedSpec]
  );
  const seed = useMemo(
    () => (selectedSpec ? seedCreateForm(selectedSpec, schema, locks, catalog) : { values: {}, fixedNodepools: 0 }),
    [selectedSpec, schema, locks, catalog]
  );
  // A flavor's nodepool ratio: one size sets the sized nodepools' replicas (ADR-0040)
  const ratio = useMemo(() => sizingRatio(selectedSpec), [selectedSpec]);
  const unsized = dynamicValues ?? seed.values;
  const sizeText = sizeInput ?? String(ratio.length > 0 ? startingSize(seed.values, ratio) : 1);
  const size = /^\d+$/.test(sizeText.trim()) && Number(sizeText) >= 1 ? Number(sizeText) : null;
  const formValues = ratio.length > 0 && size !== null ? withSize(unsized, ratio, size) : unsized;
  const presets = useMemo(
    () => (selectedSpec ? presetPaths(selectedSpec, schema, locks) : new Set<string>()),
    [selectedSpec, schema, locks]
  );
  const lockedPaths = useMemo(() => new Set(locks.values.keys()), [locks]);
  const nodepoolCount = Array.isArray(formValues[NODEPOOLS]) ? formValues[NODEPOOLS].length : 0;
  // Under the rule each nodepool's config names are fixed, its nm-conf hardware is chosen
  const lockLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    if (locks.rule) for (let i = 0; i < nodepoolCount; i++) labels[nodepoolConfigsPath(i)] = "names locked";
    return labels;
  }, [locks, nodepoolCount]);
  const growableLists = useMemo(
    () => (nodepoolsField ? { [NODEPOOLS]: { fixed: seed.fixedNodepools, create: () => newNodepool(schema, locks, catalog) } } : undefined),
    [nodepoolsField, seed.fixedNodepools, schema, locks, catalog]
  );

  // The owner placement ranks by: the mador, or the flavor's when it locks one (ADR-0028)
  const mador = placementOwner(locks.values.has(OWNER_MADOR) ? locks.values.get(OWNER_MADOR) : formValues[OWNER_MADOR]);
  const rankOwner = useDebounced(mador, OWNER_DEBOUNCE_MS);
  // The servers the cluster needs: each nodepool's InfraEnv and the replicas the form shows (a ratio's
  // included, a lock's applied), as `need`s; debounced as one string, so a new array is not a new read
  const needsKey = useMemo(
    () => placementNeeds(requestVariables(formValues, locks)[NODEPOOLS]).join(" "),
    [formValues, locks]
  );
  const rankNeedsKey = useDebounced(needsKey, OWNER_DEBOUNCE_MS);
  const rankNeeds = useMemo(() => (rankNeedsKey ? rankNeedsKey.split(" ") : []), [rankNeedsKey]);
  const placementRead = usePlacement(
    placementMode && versionsFresh && ocpVersion.trim()
      ? { site, env, version: ocpVersion.trim(), owner: rankOwner, flavor: flavorName, needs: rankNeeds }
      : null
  );
  const placement = placementRead.data ?? undefined;
  // The numbers for the previous inputs stay on screen while the new ones load
  const placementPending =
    placementRead.isLoading || placementRead.isPlaceholderData || mador !== rankOwner || needsKey !== rankNeedsKey;
  const pick = placement?.pick ?? null;
  // An admin's other choice counts while it passes every check and is not the pick (decision 15)
  const overridden =
    mceOverride && placement?.candidates.some((c) => c.mce === mceOverride && c.eligible && !c.picked) ? mceOverride : null;
  const placedMce = overridden ?? pick;
  const mce = placementMode ? (placedMce ?? "") : fallbackMce;
  const selectedMce = mces.find((m) => m.name === mce);

  // A free name from the flavor, the chosen site and the chosen MCE's env, with the next letter (ADR-0040)
  const suggestMce = placementMode ? placedMce : mceChoice;
  const suggestFor = step === "vars" && selectedSpec && siteChoice && suggestMce
    ? { site: siteChoice, mce: suggestMce, flavor: selectedSpec.metadata.name }
    : null;
  const { data: suggestion } = useQuery<NameSuggestion>({
    queryKey: ["name-suggestion", suggestFor],
    queryFn: () =>
      api.get<NameSuggestion>(`/api/day1/clusters/name-suggestion?${new URLSearchParams(suggestFor ?? {}).toString()}`),
    enabled: suggestFor !== null,
    staleTime: 10_000,
    retry: false,
  });
  const suggestedName = suggestFor && suggestion?.name ? suggestion.name : null;
  const shownName = nameEdited ? clusterName : (suggestedName ?? clusterName);
  const trimmedName = shownName.trim();

  // InfraEnvs on the MCE hub; `null` when live status is off (then the field is free text).
  const { data: infraEnvs, isLoading: infraEnvsLoading, error: infraEnvsError } = useQuery<string[] | null>({
    queryKey: ["mce-infraenvs", mce],
    queryFn: async () => {
      try {
        return await api.get<string[]>(`/api/day1/mces/${encodeURIComponent(mce)}/infraenvs`);
      } catch (error) {
        if (isApiError(error, "FEATURE_DISABLED")) return null;
        throw error;
      }
    },
    enabled: Boolean(mce) && step === "vars",
    staleTime: 60_000,
    retry: false,
  });
  const chartName = chartClusterName(trimmedName);

  // Problems at their fields: day1's (while the field still holds what was sent), and the owners' as typed
  const placed = formError?.kind === "server" ? formError.placed : undefined;
  const unchanged = (path: string) =>
    placed !== undefined && JSON.stringify(lookup(formValues, path)) === JSON.stringify(lookup(placed.values, path));
  const liveOwners = ownerProblems(formValues, schema, locks);
  const fieldProblems: Record<string, string[]> = {};
  for (const [path, lines] of Object.entries(placed?.byField ?? {})) if (unchanged(path)) fieldProblems[path] = lines;
  for (const [path, problem] of Object.entries(liveOwners)) (fieldProblems[path] ??= []).push(problem);

  const renderInput = ({ field, path, value, onChange, locked }: FieldInputContext) => {
    const sized = sizedIndex(path, ratio);
    if (sized !== null) {
      return (
        <p data-testid={`nodepool-${sized}-replicas-sized`} className="text-sm">
          <span className="font-mono font-medium">{size !== null ? String(value) : "—"}</span>
          <span className="ml-2 text-xs text-muted-foreground">ratio {ratio[sized]} × size {size ?? "?"}</span>
        </p>
      );
    }
    if (OWNER_INPUTS.includes(path) && !locked) {
      return <OwnerInput field={field} value={value} onChange={onChange} invalid={path in liveOwners} />;
    }
    if (!isConfigsPath(path)) return undefined;
    const index = Number(/\[(\d+)\]/.exec(path)?.[1] ?? 0);
    return (
      <ConfigListEditor
        entries={asEntries(value)}
        onChange={(entries) => onChange(formEntries(entries))}
        catalog={catalog}
        loading={catalogLoading}
        readOnly={locked}
        namesLocked={locks.rule !== null}
        clusterName={chartName || undefined}
        problems={unchanged(path) ? placed?.byEntry[path] : undefined}
        label={`Nodepool ${index + 1} configs`}
        hideLabel
        testId={`nodepool-${index}-configs`}
      />
    );
  };

  // A failed MCE read is not "no MCE of this env": check the name only against MCEs that loaded.
  const namingIssues = trimmedName
    ? nameProblems(trimmedName, site, selectedMce, site && !mcesLoading && !mcesError ? mces : undefined)
    : [];
  const namePlaceholder = `ocp4-${selectedMce?.env ?? "<env>"}-<name>-${site || "<site>"}-<letter>`;

  const showError = (error: FormError) => {
    setFormError(error);
    requestAnimationFrame(() => {
      // The first field day1 is about, when there is one; else the list above the submit button
      const field = error.kind === "server" && error.placed
        ? document.querySelector('[data-field-path] [role="alert"]')
        : null;
      (field ?? errorRef.current)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  /** A failed preview or create, with day1's problems placed at the fields of the form that was sent. */
  const showFailure = (error: unknown, what: "preview" | "create") => {
    const placed = placeFailure(error, schema, submitted.current ?? formValues);
    showError({ ...describeFailure(error, what), ...(placed ? { placed } : {}) });
    // Day1 checked the MCE against numbers read now: show the person those numbers too (ADR-0050)
    if (placementMode) queryClient.invalidateQueries({ queryKey: ["placement"] });
  };

  const previewMutation = useMutation({
    mutationFn: (request: CreateClusterRequest) => api.post<ClusterPreview>("/api/day1/clusters/preview", request),
    onSuccess: (preview, request) => setReviewed({ request, preview }),
    onError: (error) => showFailure(error, "preview"),
  });

  // What Create does here: Wingman's merge request, or the provision-cluster workflow (ADR-0042)
  const { data: provisioner } = useProvisioner();
  const byWorkflow = provisioner?.mode === "workflow";
  const [startedRun, setStartedRun] = useState<ProvisionRun | null>(null);

  const createMutation = useMutation({
    mutationFn: (request: CreateClusterRequest) => api.post<MRDetail | ProvisionRun>("/api/day1/clusters", request),
    onSuccess: (result) => {
      setReviewed(null);
      if (isProvisionRun(result)) {
        toast.success(`provision-cluster started for ${result.cluster}`, {
          description: "The workflow reserves the segment and opens the merge request; follow it here.",
        });
        setStartedRun(result);
        return;
      }
      const mr = result;
      toast.success(`MR !${mr.iid} opened: ${mr.title}`, {
        description: "CI and the allocate-segment workflow add their keys to its branch; another admin approves it after.",
      });
      setReviewed(null);
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      router.push(approvalHref(mr));
    },
    onError: (error) => {
      setReviewed(null);
      showFailure(error, "create");
    },
  });

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3 text-center">
        <p className="text-lg font-semibold">Insufficient permissions</p>
        <p className="text-sm text-muted-foreground">Your role (viewer) does not have access to create clusters.</p>
        <Link href="/clusters" className={buttonVariants({ variant: "outline", size: "sm" })}>Back to clusters</Link>
      </div>
    );
  }

  // Workflow mode: the cluster has no file until the workflow's merge request is merged, so its run is shown here
  if (startedRun) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-6 sm:px-6 lg:px-8">
        <ProvisionRunPanel started={startedRun} />
        <div className="flex flex-wrap gap-2">
          <Link href="/clusters" className={buttonVariants({ variant: "outline", size: "sm" })}>Back to clusters</Link>
          <button
            type="button"
            onClick={() => setStartedRun(null)}
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Create another cluster
          </button>
        </div>
      </div>
    );
  }

  const handleSelectSpec = (spec: SpecEntry) => {
    setSelectedSpec(spec);
    setOcpChoice(null);
    setDynamicValues(null);
    setSizeInput(null);
    setFormError(null);
    setMceOverride(null);
    setOverrideReason("");
    setReasonMissing(false);
    submitted.current = null;
    const overrides: Record<string, Record<string, unknown>> = {};
    for (const addon of spec.spec.day2.addons) {
      const defaults = defaultOverrides(addon.overrideable ?? []);
      if (Object.keys(defaults).length > 0) overrides[`${addon.team}/${addon.name}`] = defaults;
    }
    setAddonOverrides(overrides);
    setOverrideModes({});
    setAddonYamlText({});
    setStep("vars");
  };

  /** The addon overrides to send, or the problems that stop the request. */
  const collectOverrides = (): { overrides: Record<string, Record<string, unknown>>; problems: string[] } => {
    const overrides: Record<string, Record<string, unknown>> = {};
    const problems: string[] = [];
    for (const addon of selectedSpec?.spec.day2.addons ?? []) {
      const key = `${addon.team}/${addon.name}`;
      let values: Record<string, unknown>;
      if (overrideModes[key] === "yaml") {
        try {
          const parsed = jsYaml.load(addonYamlText[key] ?? "");
          if (parsed !== null && parsed !== undefined && (typeof parsed !== "object" || Array.isArray(parsed))) {
            problems.push(`${key}: the values must be a YAML mapping`);
            continue;
          }
          values = (parsed as Record<string, unknown> | null) ?? {};
        } catch (e) {
          problems.push(`${key}: the values are not valid YAML (${(e as Error).message.split("\n")[0]})`);
          continue;
        }
      } else {
        values = pruneEmpty(addonOverrides[key] ?? {});
      }
      if (Object.keys(values).length > 0) overrides[key] = values;
    }
    return { overrides, problems };
  };

  const handleReview = () => {
    setFormError(null);
    const problems: string[] = [];
    const reason = cleanReason(overrideReason);
    if (!site) problems.push("Choose a site");
    if (!placementMode) {
      if (!mce) problems.push("Choose an MCE");
    } else if (!env) {
      problems.push("Choose the environment: prod or prep");
    }
    if (!trimmedName) problems.push("Enter a cluster name");
    if (ratio.length > 0 && size === null) problems.push("Enter the nodepools' size: a whole number of at least 1");
    if (!ocpVersion.trim()) problems.push("Choose an OpenShift version");
    // The MCE Wingman picked, or an admin's other choice with its reason (ADR-0050, decision 15)
    if (placementMode && site && env && ocpVersion.trim()) {
      if (placementRead.isError && !placement) problems.push("Wingman could not pick the MCE: try again, under MCE");
      // Numbers for another version or env are not sent; a pick an owner just typed would move is day1's 409
      else if (!placement || placementRead.isPlaceholderData) problems.push("Wingman is still picking the MCE");
      else if (!mce) problems.push(`No ${env} MCE on ${site} can take this cluster: see MCE`);
      else if (overridden && !reason) problems.push(`Say why ${overridden} instead of Wingman's pick ${pick}, under MCE`);
    }
    setReasonMissing(Boolean(overridden) && !reason);
    // Without the template's inputs the form can neither show nor check them: never send without them.
    if (schemaError) problems.push("The cluster template's inputs could not be loaded: reload the page to try again");
    else if (!templateSchema) problems.push("The cluster template's inputs are still loading");
    problems.push(...missingRequired(schema, formValues, locks.values).map((path) => `${labelForPath(path)} is required`));
    if (hasConfigs && catalogLoading) problems.push("The machine configs are still loading");
    problems.push(...flavorProblems(formValues, schema, locks, catalog, labelForPath));
    const { overrides, problems: overrideProblems } = collectOverrides();
    problems.push(...overrideProblems);
    if (problems.length > 0) {
      showError({ kind: "form", lines: problems });
      return;
    }
    submitted.current = formValues;
    previewMutation.mutate({
      name: trimmedName,
      site,
      mce,
      spec_name: selectedSpec!.metadata.name,
      spec_version: selectedSpec!.metadata.version,
      // Locked values exactly as the flavor has them; config entries and owners as day1 reads them
      variables: { ...requestVariables(formValues, locks), openshift_release_version: ocpVersion.trim() },
      ...(Object.keys(overrides).length > 0 ? { addon_overrides: overrides } : {}),
      // Day1 runs the placement again: the pick shown, so a changed pick is a 409, not a silent move
      ...(placementMode ? { placement: { pick, reason: overridden ? reason : null } } : {}),
    });
  };

  /** Choose an MCE of the placement: the pick drops any other choice (its reason is kept, in case). */
  const chooseMce = (value: string) => {
    setMceOverride(value === pick ? null : value);
    setReasonMissing(false);
  };

  /** Focus the owner's mador, which placement ranks by. */
  const focusOwner = () => {
    const input = document.querySelector<HTMLInputElement>(`[data-testid="owner-input-${OWNER_MADOR}"]`);
    input?.focus();
    input?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const reloadSpecs = () => {
    queryClient.invalidateQueries({ queryKey: ["specs"] });
    setFormError(null);
    setSelectedSpec(null);
    setStep("spec");
  };

  const toggleYamlMode = (addonKey: string, enable: boolean, catalogDefaults: Record<string, unknown>) => {
    if (enable) {
      // Seed the editor: current overrides, else the chart's defaults
      const current = addonOverrides[addonKey] ?? {};
      const base = Object.keys(current).length > 0 ? current : catalogDefaults;
      setAddonYamlText((prev) => ({ ...prev, [addonKey]: Object.keys(base).length > 0 ? jsYaml.dump(base, { lineWidth: 120 }) : "" }));
    } else {
      try {
        const parsed = jsYaml.load(addonYamlText[addonKey] ?? "");
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          setAddonOverrides((prev) => ({ ...prev, [addonKey]: parsed as Record<string, unknown> }));
        }
      } catch { /* keep the last valid overrides */ }
    }
    setOverrideModes((prev) => ({ ...prev, [addonKey]: enable ? "yaml" : "fields" }));
  };

  // The review dialog shows the request that was previewed, which is what Confirm sends.
  const reviewedOverrides = reviewed?.request.addon_overrides ?? {};
  const reviewedVariables = Object.entries(reviewed?.request.variables ?? {}).filter(
    ([k]) => k !== "openshift_release_version"
  );
  const pending = previewMutation.isPending;

  // ── The Cluster Details card's fields, ordered by mode below ────────────────

  const siteField = (
    <div className="space-y-1.5 min-w-0">
      <label id={siteLabelId} className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Site <span className="text-destructive">*</span>
      </label>
      <Combobox
        size="lg"
        options={siteOptions}
        value={site || null}
        onValueChange={(v) => { setSiteChoice(v); setMceChoice(null); setMceOverride(null); }}
        disabled={sitesLoading || sites.length === 0}
        placeholder={
          sitesLoading ? "Loading sites…"
            : sitesError ? "Sites could not be loaded"
            : sites.length === 0 ? "No sites in the day1 repo"
            : "Select site…"
        }
        searchPlaceholder="Search sites…"
        emptyMessage="No site matches."
        data-testid="site-select"
        aria-labelledby={siteLabelId}
      />
      {!siteChoice && detectedSite && (
        <p className="text-[11px] text-muted-foreground">Detected from the cluster name</p>
      )}
      {Boolean(sitesError) && <ProblemList error={sitesError} title="The sites could not be loaded" />}
    </div>
  );

  const mceField = (
    <div className="space-y-1.5 min-w-0">
      <label id={mceLabelId} className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        MCE <span className="text-destructive">*</span>
      </label>
      <Combobox
        size="lg"
        options={mceOptions}
        value={mce || null}
        onValueChange={(v) => {
          // Choosing an MCE pins its site too, so editing the name no longer moves either.
          setSiteChoice(site);
          setMceChoice(v);
        }}
        disabled={!site || mcesLoading || mces.length === 0}
        placeholder={
          !site ? "Select site first…"
            : mcesLoading ? "Loading MCEs…"
            : mcesError ? "MCEs could not be loaded"
            : mces.length === 0 ? "No MCEs on this site"
            : "Select MCE…"
        }
        searchPlaceholder="Search MCEs…"
        emptyMessage="No MCE matches."
        data-testid="mce-select"
        aria-labelledby={mceLabelId}
      />
      {!mceChoice && detectedMce && (
        <p className="text-[11px] text-muted-foreground">Detected from the cluster name</p>
      )}
      {Boolean(mcesError) && <ProblemList error={mcesError} title={`The MCEs of ${site} could not be loaded`} />}
    </div>
  );

  // With placement: prod or prep, a native radio group (arrow keys move the choice)
  const envField = (
    <div className="space-y-1.5 min-w-0">
      <span id={envLabelId} className="block text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Environment <span className="text-destructive">*</span>
      </span>
      <div
        role="radiogroup"
        aria-labelledby={envLabelId}
        data-testid="env-select"
        className="grid h-9.5 grid-cols-2 gap-0.5 rounded-lg border border-input p-0.5"
      >
        {PLACEMENT_ENVS.map((value) => (
          <label
            key={value}
            className={cn(
              "flex cursor-pointer items-center justify-center rounded-md text-sm font-medium transition-colors",
              "has-focus-visible:ring-2 has-focus-visible:ring-primary/50",
              env === value ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            )}
          >
            <input
              type="radio"
              name="cluster-env"
              value={value}
              checked={env === value}
              onChange={() => { setEnvChoice(value); setMceOverride(null); }}
              className="sr-only"
            />
            {value === "prod" ? "Prod" : "Prep"}
          </label>
        ))}
      </div>
      {!envChoice && detectedEnv && (
        <p className="text-[11px] text-muted-foreground">Detected from the cluster name</p>
      )}
    </div>
  );

  const offConventionNote = offConventionMces.length > 0 && (
    <p className="text-xs text-muted-foreground flex items-start gap-1.5" data-testid="off-convention-mces">
      <Info className="h-3.5 w-3.5 shrink-0 mt-px" />
      <span className="min-w-0 break-words">
        {offConventionMces.map((m) => m.name).join(", ")} {offConventionMces.length === 1 ? "does" : "do"} not
        follow ocp4-&lt;env&gt;-mce-{site}-&lt;letter&gt;; Wingman creates clusters only under MCEs that do.
      </span>
    </p>
  );

  const mceWarnings = selectedMce && (selectedMce.stray_files.length > 0 || selectedMce.problems.length > 0) && (
    <div className="rounded-lg border border-status-warning/30 bg-status-warning/5 px-3.5 py-3 text-xs text-status-warning-fg space-y-1" data-testid="mce-warnings">
      <p className="font-medium flex items-center gap-1.5">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        {selectedMce.name} needs attention
      </p>
      <ul className="list-disc pl-5 space-y-0.5">
        {selectedMce.stray_files.map((f) => (
          <li key={f} className="break-all">
            <span className="font-mono">{f}</span> is in hostedClusters/ but is not a cluster file; it breaks the MCE&apos;s ApplicationSet
          </li>
        ))}
        {selectedMce.problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
      </ul>
    </div>
  );

  const nameField = (className: string) => (
    <div className={className}>
      <label htmlFor="cluster-name" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Cluster Name <span className="text-destructive">*</span>
      </label>
      <input
        id="cluster-name"
        type="text"
        data-testid="cluster-name-input"
        className={cn(inputCls, "font-mono")}
        placeholder={namePlaceholder}
        value={shownName}
        onChange={(e) => {
          setClusterName(e.target.value);
          setNameEdited(true);
        }}
        autoComplete="off"
        spellCheck={false}
        aria-describedby="cluster-name-hint"
        aria-invalid={namingIssues.length > 0}
      />
      {!nameEdited && suggestedName && (
        <p data-testid="name-suggested" className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Sparkles className="h-3 w-3 shrink-0" aria-hidden />
          Suggested from flavor {selectedSpec?.metadata.name}, {siteChoice} and the MCE&apos;s env, with the next free
          letter. Type to change it.
        </p>
      )}
      {nameEdited && suggestedName && trimmedName !== suggestedName && (
        <button
          type="button"
          data-testid="use-suggested-name"
          onClick={() => {
            setNameEdited(false);
            setClusterName("");
          }}
          className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
        >
          <RotateCcw className="h-3 w-3" aria-hidden />
          Use the suggested name <span className="font-mono">{suggestedName}</span>
        </button>
      )}
      {!nameEdited && suggestFor && suggestion && !suggestion.name && suggestion.problems.length > 0 && (
        <p data-testid="name-suggestion-problems" className="text-[11px] text-muted-foreground">
          No name to suggest: {suggestion.problems.join("; ")}
        </p>
      )}
      <div id="cluster-name-hint" data-testid="naming-hint" className="text-[11px] leading-relaxed">
        {!trimmedName ? (
          <p className="text-muted-foreground">
            Format <span className="font-mono">ocp4-&lt;env&gt;-&lt;name&gt;-&lt;site&gt;-&lt;letter&gt;</span>; the env must be the MCE&apos;s, the letter one of a to z.
          </p>
        ) : namingIssues.length > 0 ? (
          <ul className="text-status-warning-fg space-y-0.5">
            {namingIssues.map((p) => (
              <li key={p} className="flex items-start gap-1.5">
                <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
                <span className="break-words">{p}</span>
              </li>
            ))}
          </ul>
        ) : site && selectedMce ? (
          <p className="text-status-ready-fg flex items-center gap-1.5">
            <CheckCircle2 className="h-3 w-3 shrink-0" />
            Follows the naming convention
          </p>
        ) : placementMode ? (
          <p className="text-muted-foreground">Checked against the MCE once Wingman has picked it.</p>
        ) : (
          <p className="text-muted-foreground">Choose the {site ? "MCE" : "site and MCE"} to check the name against.</p>
        )}
      </div>
    </div>
  );

  // Where the version list comes from: the chosen MCE, or (with placement) the candidates together
  const versionsFrom = placementMode ? (env && site ? `the ${env} MCEs on ${site}` : "") : mce;
  const versionPlaceholder = placementMode
    ? !site ? "Choose a site first"
      : !env ? "Choose prod or prep first"
      : versionsLoading ? "Loading versions…"
      : versionOptions.length === 0 ? `No ${env} MCE on ${site} hosts a version`
      : "Select OpenShift version…"
    : !mce ? "Choose an MCE first"
      : versionsLoading ? "Loading versions…"
      : versionOptions.length === 0 ? `No versions offered on ${mce}`
      : "Select OpenShift version…";

  const versionField = (className: string) => (
    <div className={className}>
      <label id={versionLabelId} className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        OpenShift Version <span className="text-destructive">*</span>
      </label>
      {/* The MCE's releases; free text only when they could not be read (create still checks) */}
      {versionsError ? (
        <input
          type="text"
          data-testid="ocp-version-input" aria-labelledby={versionLabelId}
          className={cn(inputCls, "font-mono")}
          placeholder="e.g. 4.18.56"
          value={ocpVersion}
          onChange={(e) => setOcpChoice(e.target.value)}
        />
      ) : (
        <Combobox
          size="lg"
          options={versionOptions}
          value={ocpVersion || null}
          onValueChange={setOcpChoice}
          disabled={(placementMode ? !env : !mce) || versionsLoading || versionOptions.length === 0}
          placeholder={versionPlaceholder}
          searchPlaceholder="Search versions…"
          emptyMessage="No version matches."
          data-testid="ocp-version-select"
          aria-labelledby={versionLabelId}
        />
      )}
      {Boolean(versionsError) && (
        <ProblemList
          error={versionsError}
          title={placementMode ? "The versions could not be listed: type the version" : `The OpenShift versions of ${mce} could not be listed: type the version`}
        />
      )}
      {versionProblems.length > 0 && (
        <div data-testid="ocp-version-problems">
          <ProblemList
            lines={versionProblems}
            title={ocpVersions.length > 0 ? `Some of ${mce}'s upgrade files need attention` : `${mce} offers no OpenShift version`}
          />
        </div>
      )}
      {presetNotOffered && (
        <p className="text-[11px] text-status-warning-fg flex items-start gap-1.5" data-testid="ocp-version-preset-note">
          <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
          <span className="break-words">
            {placementMode
              ? `Spec ${selectedSpec?.metadata.name} presets ${String(presetVersion)}, which no ${env} MCE on ${site} hosts: choose a version they offer.`
              : `Spec ${selectedSpec?.metadata.name} presets ${String(presetVersion)}, which ${mce} can't host: choose a version it offers.`}
          </span>
        </p>
      )}
      <p className="text-[11px] text-muted-foreground" data-testid="ocp-version-source">
        {chosenVersion === null && versionDefault
          ? `Becomes the file's mastertag; ${versionDefault.source}.`
          : versionsFrom
          ? `Becomes the file's mastertag. The releases ${versionsFrom} can host, from the day1 repo's upgrade/ folder.`
          : "Becomes the file's mastertag. Each MCE offers the releases it can host."}
      </p>
    </div>
  );

  // Wingman's pick for the cluster, and every candidate (ADR-0050)
  const placementField = (
    <div className="space-y-2 border-t pt-4" data-testid="mce-placement">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span id={mceLabelId} className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          MCE
        </span>
        <span className="text-[11px] text-muted-foreground" data-testid="placement-owner">
          {mador && placement?.owner === mador ? (
            <>Ranked for owner <span className="font-mono text-foreground">{mador}</span></>
          ) : mador ? (
            <>Ranking for owner <span className="font-mono text-foreground">{mador}</span>…</>
          ) : (
            <>
              <button type="button" onClick={focusOwner} className="text-primary hover:underline">
                Enter the owner&apos;s mador
              </button>{" "}
              to spread this owner&apos;s clusters
            </>
          )}
        </span>
      </div>
      {!env || !ocpVersion.trim() ? (
        <p data-testid="placement-waiting" className="rounded-lg border border-dashed px-4 py-3 text-xs text-muted-foreground">
          Wingman picks the MCE from the site, the environment, the version and the owner, once{" "}
          {!env ? "the environment and the OpenShift version are" : "the OpenShift version is"} chosen.
        </p>
      ) : (
        <div
          className={cn("transition-opacity motion-reduce:transition-none", placementPending && placement && "opacity-60")}
          aria-busy={placementPending}
        >
          <MCEPlacementPanel
            placement={placement}
            loading={placementRead.isLoading || (!placement && placementPending)}
            error={placementRead.error}
            onRetry={() => void placementRead.refetch()}
            chosen={placedMce}
            onChoose={chooseMce}
            reason={overrideReason}
            onReason={(value) => {
              setOverrideReason(value.slice(0, REASON_MAX));
              if (cleanReason(value)) setReasonMissing(false);
            }}
            reasonInvalid={reasonMissing}
          />
        </div>
      )}
    </div>
  );

  return (
    <div className="p-6 lg:p-8 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href="/clusters" className={buttonVariants({ variant: "ghost", size: "icon" })} aria-label="Back to clusters">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="min-w-0">
          <h1
            className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
          >
            New Cluster
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5 truncate">
            {step === "spec" ? "Step 1 of 2 — Choose a spec" : `Step 2 of 2 — Configure "${selectedSpec?.metadata.name}"`}
          </p>
        </div>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 text-sm">
        <span className={cn("flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold",
          step === "spec" ? "bg-primary text-white" : "bg-status-ready text-white")}>
          {step === "spec" ? "1" : <CheckCircle2 className="h-4 w-4" />}
        </span>
        <span className={step === "spec" ? "font-semibold" : "text-muted-foreground"}>Choose Flavor</span>
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
          {specsLoading ? (
            Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
          ) : specsError ? (
            <ProblemList error={specsError} title="The flavors could not be loaded" />
          ) : specs?.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No flavors yet"
              description="A cluster is created from a cluster spec. Create one first."
              action={<EmptyStateLink href="/specs/new">New spec</EmptyStateLink>}
              bordered
              data-testid="specs-empty"
            />
          ) : (
            specs?.map((spec) =>
              spec.load_error ? (
                <div
                  key={spec.metadata.name}
                  data-testid={`spec-card-${spec.metadata.name}`}
                  aria-disabled="true"
                  className="w-full bg-card rounded-xl border border-dashed p-5 opacity-80"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="font-semibold break-all">{spec.metadata.name}</h3>
                      <p className="text-xs text-status-warning-fg mt-1 flex items-start gap-1.5">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-px" />
                        <span className="break-words">This spec file does not parse, so it cannot be used: {spec.load_error}</span>
                      </p>
                      {spec.load_problems && spec.load_problems.length > 0 && (
                        <ul className="mt-1.5 ml-5 list-disc text-xs text-muted-foreground space-y-0.5">
                          {spec.load_problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
                        </ul>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  key={spec.metadata.name}
                  data-testid={`spec-card-${spec.metadata.name}`}
                  onClick={() => handleSelectSpec(spec)}
                  className="w-full text-left bg-card rounded-xl border shadow-sm hover:border-primary/50 hover:shadow-md transition-all p-5 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="font-semibold group-hover:text-primary transition-colors break-all">
                        {spec.metadata.name}
                      </h3>
                      {spec.metadata.description && (
                        <p className="text-sm text-muted-foreground mt-0.5 line-clamp-2">{spec.metadata.description}</p>
                      )}
                      <p className="text-xs text-muted-foreground mt-1.5">
                        {spec.spec.day2.addons.length} addon{spec.spec.day2.addons.length !== 1 ? "s" : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="rounded-full px-2 py-0.5 text-xs bg-primary/8 text-primary font-medium max-w-32 truncate">
                        {spec.metadata.version}
                      </span>
                      <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                  </div>
                </button>
              )
            )
          )}
        </div>
      )}

      {/* Step 2: Fill variables */}
      {step === "vars" && selectedSpec && (
        <div className="space-y-6">
          {/* Where the cluster lives, its name and OCP version */}
          <div className="bg-card rounded-xl border shadow-sm p-5 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">Cluster Details</h2>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 text-primary text-xs font-medium px-2.5 py-1 border border-primary/20 min-w-0">
                <span className="truncate">{selectedSpec.metadata.name}</span>
                <span className="text-primary/60 shrink-0">{selectedSpec.metadata.version}</span>
              </span>
            </div>
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                {siteField}
                {placementMode ? envField : mceField}
              </div>
              {offConventionNote}
              {placementMode ? (
                <>
                  {versionField("space-y-1.5")}
                  {placementField}
                  {mceWarnings}
                  {nameField("space-y-1.5 border-t pt-4")}
                </>
              ) : (
                <>
                  {mceWarnings}
                  {nameField("space-y-1.5")}
                  {versionField("space-y-1.5 border-t pt-4")}
                </>
              )}
            </div>
          </div>

          {/* Cluster Configuration — structure from spec, values filled here */}
          {schemaLoading || (hasConfigs && catalogLoading) ? (
            <Skeleton className="h-48 rounded-xl" />
          ) : schemaError ? (
            <ProblemList error={schemaError} title="The cluster template's inputs could not be loaded" />
          ) : schema.length === 0 ? (
            <div className="rounded-xl border border-status-warning/30 bg-status-warning/5 p-4 text-sm text-status-warning-fg flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              The cluster template takes no inputs besides the name, site, MCE and version, or the specs project has no cluster-template.j2.
            </div>
          ) : (
            <div className="bg-card rounded-xl border shadow-sm p-5 space-y-4">
              <div>
                <h2 className="text-sm font-semibold">Cluster Configuration</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Fill in the values below. <span className="font-medium">{selectedSpec.metadata.name}</span> sets the nodepools the cluster starts with{nodepoolsField ? "; add more at the end" : ""}.
                </p>
                {(lockedPaths.size > 0 || locks.rule || presets.size > 0) && (
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground" data-testid="flavor-legend">
                    {(lockedPaths.size > 0 || locks.rule) && (
                      <span className="inline-flex items-center gap-1.5">
                        <FlavorBadge kind="locked" flavor={selectedSpec.metadata.name} />
                        the flavor&apos;s value; every cluster of it gets it
                      </span>
                    )}
                    {presets.size > 0 && (
                      <span className="inline-flex items-center gap-1.5">
                        <FlavorBadge kind="preset" flavor={selectedSpec.metadata.name} />
                        prefilled; yours to change
                      </span>
                    )}
                  </div>
                )}
                {locks.rule && (
                  <p className="mt-2 text-xs text-muted-foreground flex items-start gap-1.5" data-testid="configs-rule">
                    <Info className="h-3.5 w-3.5 shrink-0 mt-px" />
                    <span className="min-w-0 break-words">
                      Every nodepool has exactly{" "}
                      {locks.rule.map((e, i) => (
                        <span key={e.name}>
                          {i > 0 && ", "}
                          <code className="font-mono text-[11px]">{e.name}</code>
                        </span>
                      ))}
                      . The names are locked; choose each nodepool&apos;s hardware type for its {NETWORK_CONFIG}.
                    </span>
                  </p>
                )}
              </div>
              {selectedSpec.warnings && selectedSpec.warnings.length > 0 && (
                <div className="rounded-lg border border-status-warning/30 bg-status-warning/5 px-3.5 py-3 text-xs text-status-warning-fg space-y-1" data-testid="flavor-warnings">
                  <p className="font-medium flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                    {selectedSpec.metadata.name} breaks rules day1 checks when a flavor is saved; a lock among them is not enforced
                  </p>
                  <ul className="list-disc pl-5 space-y-0.5">
                    {selectedSpec.warnings.map((w, i) => <li key={i} className="break-words">{w}</li>)}
                  </ul>
                </div>
              )}
              {mce && infraEnvs === null && (
                <p data-testid="infraenv-off" className="flex items-start gap-1.5 text-xs text-muted-foreground">
                  <Info className="h-3.5 w-3.5 shrink-0 mt-px" aria-hidden />
                  Type each nodepool&apos;s InfraEnv: this deployment does not read the MCE (live status is off).
                </p>
              )}
              {ratio.length > 0 && (
                <div data-testid="nodepool-size" className="rounded-lg border bg-muted/30 px-3.5 py-3 space-y-2">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                    <label htmlFor="nodepool-size-input" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Size
                    </label>
                    <input
                      id="nodepool-size-input"
                      data-testid="nodepool-size-input"
                      type="number"
                      min={1}
                      step={1}
                      inputMode="numeric"
                      className={cn(inputCls, "w-24 font-mono")}
                      value={sizeText}
                      onChange={(e) => setSizeInput(e.target.value)}
                      aria-invalid={size === null}
                      aria-describedby="nodepool-size-hint"
                    />
                    <span className="text-xs text-muted-foreground">
                      {selectedSpec.metadata.name} sizes its first {ratio.length} nodepools{" "}
                      <span className="font-mono text-foreground">{ratio.join(":")}</span>
                    </span>
                  </div>
                  <p id="nodepool-size-hint" data-testid="nodepool-size-replicas" className="text-xs">
                    {size === null ? (
                      <span className="text-status-warning-fg">Enter a whole number of at least 1</span>
                    ) : (
                      <>
                        Replicas <span className="font-mono">{ratio.map((r) => r * size).join(" · ")}</span>
                        <span className="text-muted-foreground"> = {ratio.reduce((sum, r) => sum + r * size, 0)} nodes</span>
                      </>
                    )}
                  </p>
                </div>
              )}
              {infraEnvsError && (
                <div data-testid="infraenv-hint">
                  <ProblemList error={infraEnvsError} title={`InfraEnvs could not be listed from ${mce}; type their names below`} />
                </div>
              )}
              {hasConfigs && Boolean(catalogError) && (
                <div data-testid="machine-configs-error">
                  <ProblemList error={catalogError} title="The machine configs could not be loaded: new nodepools start without the defaults, and day1 checks the names" />
                </div>
              )}
              {hasConfigs && catalog?.nodepool_defaults.error && (
                <div data-testid="nodepool-defaults-error">
                  <ProblemList
                    lines={catalog.nodepool_defaults.problems.length > 0 ? catalog.nodepool_defaults.problems : [catalog.nodepool_defaults.error]}
                    title={`${catalog.nodepool_defaults.path} cannot be used, so new nodepools start with no machine configs`}
                  />
                </div>
              )}
              <DynamicVariableForm
                schema={schema}
                values={formValues}
                onChange={setDynamicValues}
                mode="cluster-create"
                infraEnvOptions={infraEnvs ?? undefined}
                infraEnvsLoading={infraEnvsLoading && Boolean(mce)}
                flavorName={selectedSpec.metadata.name}
                lockedPaths={lockedPaths}
                lockLabels={lockLabels}
                presetPaths={presets}
                problems={fieldProblems}
                renderInput={renderInput}
                growableLists={growableLists}
              />
            </div>
          )}

          {/* Addons and overrides */}
          {selectedSpec.spec.day2.addons.length > 0 && (
            <div className="bg-card rounded-xl border shadow-sm overflow-hidden">
              <div className="px-5 py-4 border-b bg-muted/30">
                <h2 className="text-sm font-semibold">Addon Configuration</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Values for the flavor&apos;s day2 add-ons on this cluster. They are recorded in the cluster file and used when the addons are installed.
                </p>
              </div>
              <div className="p-5 space-y-4">
                {selectedSpec.spec.day2.addons.map((addon) => {
                  const addonKey = `${addon.team}/${addon.name}`;
                  const catalogEntry = addonCatalog.find((a) => a.team === addon.team && a.name === addon.name);
                  const fields = addon.overrideable ?? [];
                  const values = addonOverrides[addonKey] ?? {};
                  const isYamlMode = overrideModes[addonKey] === "yaml";
                  const valueOf = (f: OverrideableField) => getValueAtPath(values, f.path) ?? f.default ?? "";
                  const isComplex = (f: OverrideableField) => f.type === "array" || f.type === "object" || Array.isArray(valueOf(f));
                  const ordered = [...fields.filter((f) => !isComplex(f)), ...fields.filter(isComplex)];

                  return (
                    <div key={addonKey} className="rounded-xl border bg-background overflow-hidden" data-testid={`addon-${addon.team}-${addon.name}`}>
                      <div className="flex items-center justify-between gap-3 px-4 py-3 bg-muted/20 border-b">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                            <span className="text-xs font-bold text-primary">{addon.name.charAt(0).toUpperCase()}</span>
                          </div>
                          <div className="min-w-0 flex items-center gap-2">
                            <span className="font-semibold text-sm truncate">{addon.name}</span>
                            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary font-medium shrink-0">
                              {addon.version}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">{addon.team}</span>
                          {(fields.length > 0 || catalogEntry) && (
                            <button
                              type="button"
                              onClick={() => toggleYamlMode(addonKey, !isYamlMode, catalogEntry?.default_values ?? {})}
                              className={cn(
                                "text-xs px-2 py-1 rounded border transition-colors",
                                isYamlMode
                                  ? "bg-primary/10 border-primary/30 text-primary"
                                  : "bg-muted border-border text-muted-foreground hover:text-foreground"
                              )}
                            >
                              {isYamlMode ? "Fields" : "Full Values"}
                            </button>
                          )}
                        </div>
                      </div>

                      {isYamlMode ? (
                        <div className="p-4">
                          <p className="text-xs text-muted-foreground mb-2">
                            Edit the values YAML. Every key here is recorded as an override; remove keys to keep the addon&apos;s defaults.
                          </p>
                          <textarea
                            data-testid={`override-yaml-${addon.team}-${addon.name}`}
                            className="w-full rounded-lg border bg-zinc-950 text-zinc-200 px-3 py-2.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y min-h-[200px]"
                            value={addonYamlText[addonKey] ?? ""}
                            onChange={(e) => setAddonYamlText((prev) => ({ ...prev, [addonKey]: e.target.value }))}
                            spellCheck={false}
                          />
                        </div>
                      ) : fields.length > 0 ? (
                        <div className="p-4 space-y-4">
                          {ordered.map((field) => (
                            <div key={field.path} className="space-y-1.5">
                              <label htmlFor={`override-field-${addon.team}-${addon.name}-${field.path.replace(/\./g, "-")}`} className="text-xs font-medium text-muted-foreground uppercase tracking-wide break-all">
                                {field.path}
                              </label>
                              <OverrideField
                                id={`override-field-${addon.team}-${addon.name}-${field.path.replace(/\./g, "-")}`}
                                field={field}
                                value={valueOf(field)}
                                onChange={(val) =>
                                  setAddonOverrides((prev) => ({
                                    ...prev,
                                    [addonKey]: setValueAtPath(prev[addonKey] ?? {}, field.path, val),
                                  }))
                                }
                              />
                              {field.description && (
                                <p className="text-xs text-muted-foreground">{field.description}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="px-4 py-3 text-xs text-muted-foreground italic">
                          No configurable fields defined in spec.{catalogEntry ? ' Use "Full Values" to set chart values.' : ""}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {formError && (
            <div ref={errorRef} className="space-y-2 scroll-mt-24" data-testid="form-problems">
              {formError.kind === "form" ? (
                <ProblemList lines={formError.lines} title="Some fields need attention" />
              ) : formError.placed ? (
                // Day1's problems about a field are shown there; the rest are listed here
                <ProblemList
                  error={formError.error}
                  title={formError.title}
                  lines={[
                    ...formError.placed.rest,
                    formError.placed.rest.length > 0
                      ? `And ${formError.placed.placed} more, marked at the fields they are about.`
                      : `${formError.placed.placed === 1 ? "One problem is" : `${formError.placed.placed} problems are`} marked at the fields above.`,
                  ]}
                />
              ) : (
                <ProblemList error={formError.error} title={formError.title} />
              )}
              {formError.kind === "server" && (formError.hint || formError.reloadSpec) && (
                <div className="flex items-center justify-between gap-3 px-1">
                  {formError.hint && <p className="text-xs text-muted-foreground">{formError.hint}</p>}
                  {formError.reloadSpec && (
                    <button type="button" onClick={reloadSpecs} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "shrink-0")}>
                      <RotateCcw className="h-3.5 w-3.5 mr-1.5" />Reload flavors
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <button onClick={() => { setStep("spec"); setFormError(null); }} className={buttonVariants({ variant: "outline" })}>
              <ArrowLeft className="h-4 w-4 mr-1.5" />Back
            </button>
            <button
              onClick={handleReview}
              disabled={pending}
              data-testid="review-button"
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <Eye className="h-4 w-4" />
              {pending ? "Rendering preview…" : "Review & Create"}
            </button>
          </div>
        </div>
      )}

      {/* Review dialog: exactly the file the create commits */}
      <ReviewDialog
        open={reviewed !== null}
        onOpenChange={(open) => { if (!open) setReviewed(null); }}
        title="Review: Create Cluster"
        description={
          byWorkflow
            ? "This is the file the provision-cluster workflow receives. It reserves the segment, adds vlanId and dhcp_values, pushes the file on its own branch and opens the merge request; a person merges it."
            : "This is the file the merge request adds. After it is pushed, CI and the allocate-segment workflow commit mcConfigMap, vlanId and dhcp_values to the branch; approve once they have."
        }
        onConfirm={() => reviewed && createMutation.mutate(reviewed.request)}
        isPending={createMutation.isPending}
        confirmLabel={byWorkflow ? "Confirm — Start provision-cluster" : "Confirm — Create Cluster MR"}
      >
        {reviewed && (
          <div className="rounded-lg border bg-muted/30 p-4 space-y-3 text-sm font-mono">
            <div className="space-y-1">
              <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide mb-2">Identity</p>
              {[
                ["Cluster Name", reviewed.request.name],
                ["Site", reviewed.request.site],
                ["MCE", reviewed.request.mce],
                ...(reviewed.request.placement
                  ? [[
                      "Chosen by",
                      reviewed.request.placement.reason
                        ? `You, over Wingman's pick ${reviewed.request.placement.pick}: ${reviewed.request.placement.reason}`
                        : "Wingman's pick",
                    ]]
                  : []),
                ["OpenShift", String(reviewed.request.variables.openshift_release_version ?? "")],
              ].map(([label, value]) => (
                <div key={label} className="flex gap-3">
                  <span className="text-muted-foreground w-32 shrink-0">{label}</span>
                  <span className="font-medium break-all min-w-0">{value}</span>
                </div>
              ))}
            </div>

            <div className="border-t pt-3 space-y-1">
              <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide mb-2">Flavor</p>
              <div className="flex gap-3">
                <span className="text-muted-foreground w-32 shrink-0">Name</span>
                <span className="font-medium break-all min-w-0">{reviewed.request.spec_name}</span>
              </div>
              <div className="flex gap-3">
                <span className="text-muted-foreground w-32 shrink-0">Version</span>
                <span className="font-medium">{reviewed.request.spec_version}</span>
              </div>
            </div>

            {reviewedVariables.length > 0 && (
              <div className="border-t pt-3 space-y-1">
                <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide mb-2">Variables</p>
                {reviewedVariables.map(([k, v]) => (
                  <div key={k} className="flex gap-3">
                    <span className="text-muted-foreground w-32 shrink-0 truncate">{formatVariableName(k)}</span>
                    <span className="font-medium break-all min-w-0">{summarizeValue(v)}</span>
                  </div>
                ))}
              </div>
            )}

            {selectedSpec && selectedSpec.spec.day2.addons.length > 0 && (
              <div className="border-t pt-3">
                <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Requested addons ({selectedSpec.spec.day2.addons.length})
                </p>
                <div className="space-y-2">
                  {selectedSpec.spec.day2.addons.map((addon) => {
                    const addonKey = `${addon.team}/${addon.name}`;
                    const overrides = reviewedOverrides[addonKey];
                    return (
                      <div key={addonKey}>
                        <div className="flex gap-3">
                          <span className="text-muted-foreground w-32 shrink-0 truncate">{addon.name}</span>
                          <span className="font-medium">{addon.version} · {addon.team}</span>
                        </div>
                        {overrides ? (
                          <pre className="ml-32 mt-1 pl-3 border-l-2 border-primary/20 text-xs text-foreground/80 whitespace-pre-wrap break-all">
                            {jsYaml.dump(overrides, { lineWidth: 100 }).trimEnd()}
                          </pre>
                        ) : (
                          <p className="ml-32 mt-1 pl-3 border-l-2 border-border text-xs font-sans text-muted-foreground">No override values</p>
                        )}
                      </div>
                    );
                  })}
                </div>
                <p className="mt-2 text-xs font-sans text-muted-foreground">
                  Recorded in the cluster file&apos;s header; installing them is a day2 change.
                </p>
              </div>
            )}

            <GitLabFileList
              groups={[{ label: "Day 1 repo (cluster values file)", files: [{ path: reviewed.preview.path, content: reviewed.preview.yaml }] }]}
            />
          </div>
        )}
      </ReviewDialog>
    </div>
  );
}
