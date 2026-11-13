"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import jsYaml from "js-yaml";
import { AlertCircle, Plus, X, ChevronDown, ChevronRight, Lock, Unlock, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";
import { Combobox } from "@/components/ui/combobox";
import type { TemplateField } from "@/types";

// ── Types ─────────────────────────────────────────────────────────────────────

export type Mode = "spec-build" | "cluster-create" | "cluster-edit";

export interface FieldValueMap { [key: string]: FieldValue }
export type FieldValue = string | number | boolean | FieldValue[] | FieldValueMap;
export type FormValues = FieldValueMap;

/** InfraEnv names on the MCE hub, for every `infra_env` input at any depth (e.g. inside nodepools). */
interface InfraEnvProps {
  infraEnvOptions?: string[];
  infraEnvsLoading?: boolean;
}

/** One field, as a custom input (`renderInput`) is drawn for it. */
export interface FieldInputContext {
  field: TemplateField;
  /** The template-input path: `owner_anaf`, `nodepools[1].configs`. */
  path: string;
  value: FieldValue;
  onChange: (v: FieldValue) => void;
  /** In `lockedPaths`: show the value, never an editable input. */
  locked: boolean;
}

/** A list the person may grow outside spec-build (the create form's nodepools). */
export interface GrowableList {
  /** The first `fixed` items come from the flavor and cannot be removed. */
  fixed: number;
  /** The item "Add" appends at `index`, e.g. a nodepool with the nodepool defaults. */
  create: (index: number) => FieldValueMap;
}

/**
 * What a flavor sets on the form (flavors v2, ADR-0026, ADR-0029), keyed by
 * template-input path (`owner_anaf`, `nodepools[0].configs`). All optional,
 * and ignored in spec-build: without them the form is what it was.
 */
export interface FlavorFormProps {
  /** Locked by the flavor: shown read-only with its value and a lock. */
  lockedPaths?: ReadonlySet<string>;
  /** Partly locked (the configs rule: names fixed, hardware chosen): a lock badge with this text; the input stays. */
  lockLabels?: Readonly<Record<string, string>>;
  /** Prefilled by the flavor and editable: a "preset" badge. */
  presetPaths?: ReadonlySet<string>;
  /** The flavor's name, for the badges' explanations. */
  flavorName?: string;
  /** Problems to show under a field: day1's 422 at its path, or the form's own check. */
  problems?: Readonly<Record<string, readonly string[]>>;
  /** A custom input for a field; `undefined` keeps the default one. */
  renderInput?: (ctx: FieldInputContext) => ReactNode | undefined;
  /** Lists that may grow outside spec-build, by path (`nodepools`). */
  growableLists?: Readonly<Record<string, GrowableList>>;
}

const FlavorContext = createContext<FlavorFormProps>({});

// ── Helpers ───────────────────────────────────────────────────────────────────

function defaultForField(field: TemplateField): FieldValue {
  if (field.default !== undefined && field.default !== null) {
    if (field.default === "__list__" || (Array.isArray(field.default) && (field.default as unknown[]).length === 0))
      return [];
    if (field.default === "__object__") return {};
    return field.default as FieldValue;
  }
  if (field.type === "list") return [];
  if (field.type === "object") return {};
  if (field.type === "boolean") return false;
  if (field.type === "integer") return 0;
  return "";
}

function emptyObjectForFields(fields: TemplateField[]): Record<string, FieldValue> {
  const obj: Record<string, FieldValue> = {};
  for (const f of fields) obj[f.name] = defaultForField(f);
  return obj;
}

export function seedFromStructure(structure: Record<string, unknown>, schema: TemplateField[]): FormValues {
  const vals: FormValues = {};
  for (const field of schema) {
    const specValue = structure[field.name];
    if (specValue === undefined) {
      vals[field.name] = defaultForField(field);
      continue;
    }
    if (field.type === "list" && Array.isArray(specValue)) {
      if (field.fields && field.fields.length > 0) {
        // List-of-objects: recursively seed each item so nested sub-list counts are preserved
        vals[field.name] = (specValue as unknown[]).map((itemSpec) =>
          typeof itemSpec === "object" && itemSpec !== null && !Array.isArray(itemSpec)
            ? seedFromStructure(itemSpec as Record<string, unknown>, field.fields!)
            : emptyObjectForFields(field.fields!)
        );
      } else {
        // String/primitive list: preserve count, blank values
        vals[field.name] = (specValue as unknown[]).map(() => "");
      }
    } else {
      vals[field.name] = defaultForField(field);
    }
  }
  return vals;
}

function toLabel(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Shared styles ─────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm transition-colors placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50";

/** The class of the form's text inputs, for a `renderInput` that draws its own. */
export const fieldInputClassName = inputCls;

// ── Lock toggle ───────────────────────────────────────────────────────────────

function LockToggle({ locked, onToggle }: { locked: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      title={locked ? "Immutable after create — click to unlock" : "Click to make immutable after create"}
      className={cn(
        "flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold transition-all border",
        locked
          ? "bg-amber-500/10 border-amber-400/30 text-amber-500 hover:bg-amber-500/20"
          : "bg-transparent border-transparent text-muted-foreground/40 hover:border-muted-foreground/20 hover:text-muted-foreground hover:bg-muted/50"
      )}
    >
      {locked ? <Lock className="h-2.5 w-2.5" /> : <Unlock className="h-2.5 w-2.5" />}
      {locked && <span>locked</span>}
    </button>
  );
}

// ── Immutable badge (cluster-create / cluster-edit) ────────────────────────────

function ImmutableBadge({ mode }: { mode: Mode }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold border",
      mode === "cluster-edit"
        ? "bg-amber-500/10 border-amber-400/30 text-amber-500"
        : "bg-muted/50 border-muted-foreground/15 text-muted-foreground/60"
    )}>
      <Lock className="h-2.5 w-2.5" />
      {mode === "cluster-edit" ? "immutable" : "immutable after create"}
    </span>
  );
}

// ── Flavor badges (outside spec-build) ─────────────────────────────────────────

/** A field's relation to the flavor: locked, partly locked (`label`, the configs rule) or preset. */
export function FlavorBadge({ kind, label, flavor }: { kind: "locked" | "rule" | "preset"; label?: string; flavor?: string }) {
  const by = flavor ? `flavor ${flavor}` : "the flavor";
  const title =
    kind === "locked"
      ? `Locked by ${by}: every cluster of it gets this value, and day1 refuses another`
      : kind === "rule"
      ? `Partly locked by ${by}: ${label}`
      : `Preset by ${by}: prefilled, and yours to change`;
  return (
    <span
      title={title}
      data-flavor-badge={kind}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold border",
        kind === "preset"
          ? "bg-primary/5 border-primary/15 text-primary/80"
          : "bg-amber-500/10 border-amber-400/30 text-amber-600 dark:text-amber-400"
      )}
    >
      {kind !== "preset" && <Lock className="h-2.5 w-2.5" aria-hidden />}
      {kind === "locked" ? "locked" : kind === "rule" ? label : "preset"}
    </span>
  );
}

/** A locked list's value, as YAML. */
function LockedValue({ value }: { value: FieldValue }) {
  const empty = value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
  return (
    <pre className="rounded-lg border border-input/50 bg-muted/30 px-3 py-2 text-xs font-mono text-muted-foreground whitespace-pre-wrap break-all">
      {empty ? "—" : jsYaml.dump(value, { indent: 2, lineWidth: 120 }).trimEnd()}
    </pre>
  );
}

// ── Scalar input ──────────────────────────────────────────────────────────────

function ScalarInput({
  field, value, onChange, readOnly,
}: {
  field: TemplateField; value: FieldValue; onChange: (v: FieldValue) => void; readOnly?: boolean;
}) {
  if (readOnly) {
    return (
      <div className="rounded-lg border border-input/50 bg-muted/30 px-3 py-2 text-sm text-muted-foreground select-none font-mono text-xs">
        {String(value ?? "—")}
      </div>
    );
  }

  if (field.type === "boolean") {
    return (
      <label className="flex items-center gap-2.5 cursor-pointer group w-fit">
        <div className={cn(
          "relative flex h-5 w-9 items-center rounded-full border-2 transition-colors",
          value ? "bg-primary border-primary" : "bg-muted border-input"
        )}>
          <div className={cn(
            "absolute h-3.5 w-3.5 rounded-full bg-white shadow transition-transform",
            value ? "translate-x-3.5" : "translate-x-0.5"
          )} />
          <input
            type="checkbox"
            className="sr-only"
            checked={!!value}
            onChange={(e) => onChange(e.target.checked)}
          />
        </div>
        <span className="text-sm text-muted-foreground group-hover:text-foreground transition-colors">
          {value ? "Enabled" : "Disabled"}
        </span>
      </label>
    );
  }

  if (field.type === "integer") {
    return (
      <input
        type="number"
        className={inputCls}
        value={value as number}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    );
  }

  return (
    <input
      type="text"
      className={inputCls}
      value={value as string}
      placeholder={field.example ? `e.g. ${field.example}` : String(field.default ?? "")}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// ── Object textarea ────────────────────────────────────────────────────────────

function ObjectEditor({
  field: _field, value, onChange, readOnly,
}: {
  field: TemplateField; value: FieldValue; onChange: (v: FieldValue) => void; readOnly?: boolean;
}) {
  const [raw, setRaw] = useState(() => {
    if (value === null || value === undefined || value === "" || (typeof value === "object" && !Array.isArray(value) && Object.keys(value as object).length === 0)) return "";
    if (typeof value === "string") return value;
    return jsYaml.dump(value, { indent: 2, lineWidth: 120 }).trimEnd();
  });
  const [error, setError] = useState("");

  const handleChange = (text: string) => {
    setRaw(text);
    if (!text.trim()) { setError(""); onChange(""); return; }
    try {
      const parsed = jsYaml.load(text);
      onChange(parsed as FieldValue);
      setError("");
    } catch {
      setError("Invalid YAML");
    }
  };

  if (readOnly) {
    return (
      <div className="rounded-lg border border-input/50 bg-muted/30 px-3 py-2 text-xs font-mono text-muted-foreground select-none">
        {raw || "—"}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <textarea
        className={cn(
          "w-full font-mono text-xs rounded-lg border border-input bg-muted/30 px-3 py-2.5 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 resize-y",
          error && "border-destructive focus:ring-destructive/20"
        )}
        rows={4}
        value={raw}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={_field.example ? `# Example: ${_field.example}` : "# scalar, list, or map"}
      />
      {error && <p className="text-xs text-destructive flex items-center gap-1">⚠ {error}</p>}
    </div>
  );
}

// ── Object card ───────────────────────────────────────────────────────────────

function ObjectCard({
  fields, value, onChange, onRemove, index, itemName = "item", mode, basePath, immutablePaths, onToggleImmutable,
  infraEnvOptions, infraEnvsLoading,
}: {
  fields: TemplateField[];
  value: Record<string, FieldValue>;
  onChange: (v: Record<string, FieldValue>) => void;
  /** Given when the item may be removed (spec-build, or one added to a growable list). */
  onRemove?: () => void;
  index: number;
  /** For the remove button's accessible name: "Nodepool". */
  itemName?: string;
  mode: Mode;
  basePath: string;
  immutablePaths: Set<string>;
  onToggleImmutable?: (path: string) => void;
} & InfraEnvProps) {
  const [expanded, setExpanded] = useState(true);

  // Build a one-line summary for collapsed state
  const summary = fields
    .filter((f) => value[f.name] && String(value[f.name]) !== "" && String(value[f.name]) !== "0")
    .slice(0, 3)
    .map((f) => `${toLabel(f.name)}: ${Array.isArray(value[f.name]) ? `${(value[f.name] as unknown[]).length} items` : String(value[f.name])}`)
    .join(" · ");

  return (
    <div className="rounded-xl border border-border/60 bg-card overflow-hidden shadow-sm transition-shadow hover:shadow-md">
      {/* Card header */}
      <div className={cn(
        "flex items-center gap-2 px-4 py-3 border-b border-border/40 transition-colors",
        expanded ? "bg-muted/30" : "bg-muted/10 hover:bg-muted/20 cursor-pointer"
      )}
        onClick={!expanded ? () => setExpanded(true) : undefined}
      >
        {/* Drag hint (visual only) */}
        <div className="text-muted-foreground/30 shrink-0">
          <GripVertical className="h-3.5 w-3.5" />
        </div>

        {/* Number badge */}
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary shrink-0">
          {index + 1}
        </span>

        {/* Collapse button */}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
          className="flex items-center gap-1.5 text-xs font-medium text-foreground/70 hover:text-foreground transition-colors"
        >
          {expanded
            ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          }
          {!expanded && summary
            ? <span className="text-muted-foreground font-normal truncate max-w-xs">{summary}</span>
            : null
          }
        </button>

        {/* Remove button (spec-build, or an item added to a growable list) */}
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove ${itemName.toLowerCase()} ${index + 1}`}
            className="ml-auto flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
          >
            <X className="h-3 w-3" />
            Remove
          </button>
        )}
        {!onRemove && <div className="ml-auto" />}
      </div>

      {/* Card body */}
      {expanded && (
        <div className="p-4 space-y-4 bg-card/50">
          {fields.map((subField) => (
            <FieldEditor
              key={subField.name}
              field={subField}
              value={value[subField.name] ?? defaultForField(subField)}
              onChange={(v) => onChange({ ...value, [subField.name]: v })}
              mode={mode}
              path={`${basePath}.${subField.name}`}
              immutablePaths={immutablePaths}
              onToggleImmutable={onToggleImmutable}
              infraEnvOptions={infraEnvOptions}
              infraEnvsLoading={infraEnvsLoading}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── String list editor ─────────────────────────────────────────────────────────

function StringListEditor({
  value, onChange, mode,
}: {
  value: FieldValue[]; onChange: (v: FieldValue[]) => void; mode: Mode;
}) {
  const canAdd = mode === "spec-build";

  return (
    <div className="space-y-2">
      {(value as string[]).map((item, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input
            type="text"
            className={cn(inputCls, "flex-1")}
            value={item}
            readOnly={mode === "spec-build"}
            onChange={(e) => {
              if (mode === "spec-build") return;
              const next = [...(value as string[])];
              next[i] = e.target.value;
              onChange(next);
            }}
          />
          {canAdd && (
            <button
              type="button"
              onClick={() => onChange((value as string[]).filter((_, j) => j !== i))}
              className="flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all border border-transparent hover:border-destructive/20"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      ))}
      {canAdd && (
        <button
          type="button"
          onClick={() => onChange([...(value as string[]), ""])}
          className="flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 font-medium transition-colors py-1.5 px-2 rounded-lg hover:bg-primary/5 border border-dashed border-primary/30 hover:border-primary/50 w-full justify-center"
        >
          <Plus className="h-3 w-3" />
          Add item
        </button>
      )}
    </div>
  );
}

// ── Object list editor ─────────────────────────────────────────────────────────

function ObjectListEditor({
  field, value, onChange, mode, basePath, immutablePaths, onToggleImmutable,
  infraEnvOptions, infraEnvsLoading,
}: {
  field: TemplateField;
  value: FieldValue[];
  onChange: (v: FieldValue[]) => void;
  mode: Mode;
  basePath: string;
  immutablePaths: Set<string>;
  onToggleImmutable?: (path: string) => void;
} & InfraEnvProps) {
  const subFields = field.fields!;
  const growableLists = useContext(FlavorContext).growableLists;
  const growable = mode === "spec-build" ? undefined : growableLists?.[basePath];
  const canAdd = mode === "spec-build" || growable !== undefined;
  const items = value as Record<string, FieldValue>[];
  const friendlyName = toLabel(field.name).replace(/s$/, "");
  const canRemove = (i: number) => mode === "spec-build" || (growable !== undefined && i >= growable.fixed);

  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <ObjectCard
          key={i}
          fields={subFields}
          value={item}
          index={i}
          itemName={friendlyName}
          mode={mode}
          basePath={`${basePath}[${i}]`}
          immutablePaths={immutablePaths}
          onToggleImmutable={onToggleImmutable}
          infraEnvOptions={infraEnvOptions}
          infraEnvsLoading={infraEnvsLoading}
          onChange={(updated) => {
            const next = [...items];
            next[i] = updated;
            onChange(next);
          }}
          onRemove={canRemove(i) ? () => onChange(items.filter((_, j) => j !== i)) : undefined}
        />
      ))}

      {canAdd && (
        <button
          type="button"
          data-testid={`add-${basePath}`}
          onClick={() => onChange([...items, growable ? growable.create(items.length) : emptyObjectForFields(subFields)])}
          className="flex items-center gap-2 w-full rounded-xl border-2 border-dashed border-primary/20 hover:border-primary/40 bg-primary/3 hover:bg-primary/6 px-4 py-3 text-sm font-medium text-primary/60 hover:text-primary transition-all group"
        >
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 group-hover:bg-primary/20 transition-colors">
            <Plus className="h-3.5 w-3.5 text-primary" />
          </div>
          Add {friendlyName}
        </button>
      )}

      {!canAdd && items.length === 0 && (
        <div className="rounded-xl border border-dashed border-border/50 p-4 text-center text-sm text-muted-foreground">
          No {toLabel(field.name).toLowerCase()} defined in the flavor
        </div>
      )}
    </div>
  );
}

// ── Field editor ──────────────────────────────────────────────────────────────

// eslint-disable-next-line complexity -- size baseline (ADR-0056)
function FieldEditor({
  field, value, onChange, mode, path, immutablePaths, onToggleImmutable,
  infraEnvOptions, infraEnvsLoading,
}: {
  field: TemplateField;
  value: FieldValue;
  onChange: (v: FieldValue) => void;
  mode: Mode;
  path: string;
  immutablePaths: Set<string>;
  onToggleImmutable?: (path: string) => void;
} & InfraEnvProps) {
  const flavor = useContext(FlavorContext);
  const isImmutable = immutablePaths.has(path);
  const isLocked = mode !== "spec-build" && (flavor.lockedPaths?.has(path) ?? false);
  const lockLabel = mode !== "spec-build" && !isLocked ? flavor.lockLabels?.[path] : undefined;
  const isPreset = mode !== "spec-build" && !isLocked && !lockLabel && (flavor.presetPaths?.has(path) ?? false);
  const isReadOnly = (mode === "cluster-edit" && isImmutable) || isLocked;
  const isScalar = field.type !== "list" && field.type !== "object";
  const fieldProblems = flavor.problems?.[path] ?? [];

  const renderInput = () => {
    const custom = mode === "spec-build" ? undefined : flavor.renderInput?.({ field, path, value, onChange, locked: isLocked });
    if (custom !== undefined) return custom;

    // A locked list is the flavor's value: shown, never edited
    if (isLocked && field.type === "list") return <LockedValue value={value} />;

    if (field.type === "list" && field.fields && field.fields.length > 0) {
      return (
        <ObjectListEditor
          field={field}
          value={value as FieldValue[]}
          onChange={(v) => onChange(v)}
          mode={mode}
          basePath={path}
          immutablePaths={immutablePaths}
          onToggleImmutable={onToggleImmutable}
          infraEnvOptions={infraEnvOptions}
          infraEnvsLoading={infraEnvsLoading}
        />
      );
    }

    if (field.type === "list") {
      return (
        <StringListEditor
          value={value as FieldValue[]}
          onChange={(v) => onChange(v)}
          mode={mode}
        />
      );
    }

    if (field.type === "object") {
      return <ObjectEditor field={field} value={value} onChange={onChange} readOnly={isReadOnly} />;
    }

    // Scalar — in spec-build mode, no value input (structure phase only)
    if (mode === "spec-build") return null;

    // infra_env is picked from the MCE hub's InfraEnvs when live status lists them
    if (field.name === "infra_env" && (mode === "cluster-create" || mode === "cluster-edit") && !isReadOnly) {
      if (infraEnvsLoading || (infraEnvOptions && infraEnvOptions.length > 0)) {
        return (
          <Combobox
            size="lg"
            options={(infraEnvOptions ?? []).map((env) => ({ value: env, label: env }))}
            value={typeof value === "string" ? value : null}
            onValueChange={(env) => onChange(env ?? "")}
            disabled={infraEnvsLoading}
            placeholder={infraEnvsLoading ? "Loading infra envs…" : "Select infra env…"}
            searchPlaceholder="Search infra envs…"
            emptyMessage="No infra env matches."
            aria-label={toLabel(field.name)}
            data-testid={`infra-env-select-${path}`}
          />
        );
      }
      // Live status is off or the list failed: type the name
    }

    return <ScalarInput field={field} value={value} onChange={onChange} readOnly={isReadOnly} />;
  };

  const input = renderInput();

  return (
    <div className="space-y-2" data-field-path={path}>
      {/* Label row */}
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-xs font-semibold tracking-wide uppercase text-foreground/60">
          {toLabel(field.name)}
          {field.required && <span className="text-destructive ml-0.5">*</span>}
          {!field.required && (
            <span className="ml-1.5 text-[10px] font-normal normal-case text-muted-foreground/60 tracking-normal">optional</span>
          )}
        </label>

        {/* Lock controls */}
        {mode === "spec-build" && isScalar && (
          <LockToggle locked={isImmutable} onToggle={() => onToggleImmutable?.(path)} />
        )}
        {(mode === "cluster-create" || mode === "cluster-edit") && isImmutable && !isLocked && (
          <ImmutableBadge mode={mode} />
        )}
        {isLocked && <FlavorBadge kind="locked" flavor={flavor.flavorName} />}
        {lockLabel && <FlavorBadge kind="rule" label={lockLabel} flavor={flavor.flavorName} />}
        {isPreset && <FlavorBadge kind="preset" flavor={flavor.flavorName} />}
      </div>

      {/* Input — hidden for scalars in spec-build mode */}
      {input}

      {fieldProblems.length > 0 && (
        <ul role="alert" data-field-problems className="space-y-0.5 text-xs text-destructive">
          {fieldProblems.map((problem, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <AlertCircle className="h-3 w-3 shrink-0 mt-0.5" aria-hidden />
              <span className="min-w-0 break-words">{problem}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Example hint — shown below object/list fields (scalar uses placeholder instead) */}
      {field.example && input !== null && (field.type === "object" || field.type === "list") && (
        <p className="text-[11px] text-muted-foreground/60 flex items-center gap-1.5">
          <span className="font-semibold text-muted-foreground/50">e.g.</span>
          <code className="font-mono">{field.example}</code>
        </p>
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function DynamicVariableForm({
  schema, values, onChange,
  mode = "cluster-create",
  immutablePaths = new Set(),
  onToggleImmutable,
  infraEnvOptions,
  infraEnvsLoading,
  lockedPaths,
  lockLabels,
  presetPaths,
  flavorName,
  problems,
  renderInput,
  growableLists,
}: {
  schema: TemplateField[];
  values: FormValues;
  onChange: (values: FormValues) => void;
  mode?: Mode;
  immutablePaths?: Set<string>;
  onToggleImmutable?: (path: string) => void;
} & InfraEnvProps & FlavorFormProps) {
  if (schema.length === 0) return null;

  const flavor = { lockedPaths, lockLabels, presetPaths, flavorName, problems, renderInput, growableLists };
  return (
    <FlavorContext.Provider value={flavor}>
    <div className="space-y-5">
      {schema.map((field) => (
        <FieldEditor
          key={field.name}
          field={field}
          value={values[field.name] ?? defaultForField(field)}
          onChange={(v) => onChange({ ...values, [field.name]: v })}
          mode={mode}
          path={field.name}
          immutablePaths={immutablePaths}
          onToggleImmutable={onToggleImmutable}
          infraEnvOptions={infraEnvOptions}
          infraEnvsLoading={infraEnvsLoading}
        />
      ))}
    </div>
    </FlavorContext.Provider>
  );
}
