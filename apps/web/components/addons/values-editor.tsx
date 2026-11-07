"use client";

import { useMemo, useState } from "react";
import { AlignJustify, Code2, RotateCcw, Search } from "lucide-react";
import jsYaml from "js-yaml";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { RoleChip } from "@/components/addons/role-chip";
import { roleStyle } from "@/lib/day2";
import { cn } from "@/lib/utils";
import {
  getAt,
  hasAt,
  isMapping,
  leaves,
  parseValuesYaml,
  pathLabel,
  sameValues,
  setAt,
  sourceAt,
  toYaml,
  unsetAt,
  type ValuePath,
  type Values,
} from "@/lib/values";
import type { ValuesPreview } from "@/types/day2";

type Mode = "form" | "yaml";

/** The file an edit writes, and the role its layer has in the stack. */
export interface EditedFile {
  role: string;
  path: string;
}

/** Above this many keys, a filter box appears. */
const FILTER_THRESHOLD = 10;

/**
 * The merged values of a chart on a destination, each with the layer that set
 * it, and an editor for the one file this change writes (`file`).
 *
 * The form shows every merged value; editing one writes it into `file`, and
 * "inherit" takes it out again so the layers below decide. The YAML view edits
 * `file` verbatim. The merged values come from the service (`preview`), which
 * merges exactly as Helm does; this component never merges.
 */
export function ValuesEditor({
  preview,
  loading,
  stale,
  file,
  draft,
  baseline,
  onDraftChange,
}: {
  preview: ValuesPreview | undefined;
  loading: boolean;
  /** The preview is for an older draft (a newer one is on its way). */
  stale: boolean;
  file: EditedFile;
  draft: Values;
  /** The file as it is now, to mark what this edit changes. */
  baseline: Values;
  /** Absent: read-only. */
  onDraftChange?: (next: Values) => void;
}) {
  const [mode, setMode] = useState<Mode>("form");
  const [yamlText, setYamlText] = useState("");
  const [yamlError, setYamlError] = useState("");
  const [filter, setFilter] = useState("");
  const readOnly = !onDraftChange;

  const rows = useMemo(() => {
    const merged = preview?.merged ?? {};
    const out = leaves(merged).map((l) => l.path);
    // A key the draft sets that the merge dropped (a null) or has not seen yet.
    for (const l of leaves(draft)) if (!hasAt(merged, l.path)) out.push(l.path);
    return out;
  }, [preview, draft]);

  const needle = filter.trim().toLowerCase();
  const shown = needle ? rows.filter((p) => pathLabel(p).toLowerCase().includes(needle)) : rows;

  function switchMode(next: Mode) {
    if (next === mode) return;
    if (next === "yaml") {
      setYamlText(toYaml(draft));
      setYamlError("");
    } else if (yamlError) {
      return;
    }
    setMode(next);
  }

  function editYaml(text: string) {
    setYamlText(text);
    const parsed = parseValuesYaml(text);
    if (parsed.ok) {
      setYamlError("");
      onDraftChange?.(parsed.values);
    } else {
      setYamlError(parsed.error);
    }
  }

  if (loading && !preview) {
    return (
      <div className="space-y-1.5" aria-busy>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 text-xs text-muted-foreground">
          {readOnly ? "Values" : "Writes"}{" "}
          <code className="break-all rounded bg-muted px-1 py-px font-mono text-[11px] text-foreground">{file.path}</code>
        </p>
        {!readOnly && (
          <div className="inline-flex shrink-0 rounded-lg border bg-muted/40 p-0.5" role="group" aria-label="Editor view">
            {(
              [
                ["form", "Form", AlignJustify],
                ["yaml", "YAML", Code2],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                type="button"
                onClick={() => switchMode(value)}
                aria-pressed={mode === value}
                disabled={value === "form" && Boolean(yamlError)}
                title={value === "form" && yamlError ? "Fix the YAML first" : undefined}
                className={cn(
                  "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50",
                  mode === value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="h-3 w-3" />
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {preview?.chart.problem && (
        <p className="rounded-lg border border-status-warning/30 bg-status-warning/8 px-3 py-2 text-xs text-status-warning-fg">
          Chart defaults are missing: {preview.chart.problem}
        </p>
      )}

      {mode === "yaml" ? (
        <div className="space-y-1">
          <textarea
            aria-label={`Contents of ${file.path}`}
            className={cn(
              "min-h-40 w-full resize-y rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/50",
              yamlError && "border-destructive/60",
            )}
            rows={Math.min(24, Math.max(8, yamlText.split("\n").length + 1))}
            value={yamlText}
            placeholder={"# Empty: every value is inherited.\nreplicas: 2"}
            onChange={(e) => editYaml(e.target.value)}
            spellCheck={false}
          />
          {yamlError ? (
            <p className="text-xs text-destructive" role="alert">
              {yamlError}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Only what is written here goes into the file; every other value is inherited. <code>null</code> deletes
              a key, even a chart default.
            </p>
          )}
        </div>
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">
          No values: the chart and its layers set none.{!readOnly && " Use the YAML view to add some."}
        </p>
      ) : (
        <>
          {rows.length > FILTER_THRESHOLD && (
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder={`Filter ${rows.length} keys…`}
                aria-label="Filter keys"
                className="h-8 w-full rounded-lg border bg-card pl-8 pr-3 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
          )}
          <div
            className={cn(
              "overflow-hidden rounded-lg border text-xs transition-opacity duration-150",
              stale && "opacity-70",
            )}
            aria-busy={stale || undefined}
          >
            <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_7.5rem] border-b bg-muted/40 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              <div className="px-3 py-1.5">Key</div>
              <div className="border-l px-3 py-1.5">Value</div>
              <div className="border-l px-3 py-1.5">Set by</div>
            </div>
            {shown.map((path) => (
              <ValueRow
                key={JSON.stringify(path)}
                path={path}
                preview={preview}
                file={file}
                draft={draft}
                baseline={baseline}
                onDraftChange={onDraftChange}
              />
            ))}
            {shown.length === 0 && (
              <p className="px-3 py-4 text-center text-muted-foreground">No key matches “{filter}”.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ValueRow({
  path,
  preview,
  file,
  draft,
  baseline,
  onDraftChange,
}: {
  path: ValuePath;
  preview: ValuesPreview | undefined;
  file: EditedFile;
  draft: Values;
  baseline: Values;
  onDraftChange?: (next: Values) => void;
}) {
  const own = hasAt(draft, path);
  const value = own ? getAt(draft, path) : getAt(preview?.merged, path);
  const role = own ? file.role : sourceAt(preview?.provenance, path);
  const edited = own !== hasAt(baseline, path) || !sameValues(getAt(draft, path), getAt(baseline, path));
  const label = pathLabel(path);
  const commit = onDraftChange ? (next: unknown) => onDraftChange(setAt(draft, path, next)) : undefined;

  return (
    <div
      className={cn(
        "grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_7.5rem] border-b border-l-2 last:border-b-0",
        own ? roleStyle(file.role).edge : "border-l-transparent",
      )}
      data-testid={`value-row-${label}`}
    >
      <div className="flex min-w-0 items-start gap-1.5 px-3 py-2">
        <span className="break-all font-mono leading-4 text-muted-foreground" title={label}>
          {label}
        </span>
        {edited && <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" title="Changed by this edit" />}
      </div>
      <div className="flex min-w-0 items-center border-l px-2 py-1">
        <ValueInput value={value} label={label} onCommit={commit} />
      </div>
      <div className="flex min-w-0 items-center justify-between gap-1 border-l px-2 py-1">
        <RoleChip role={role} path={own ? file.path : layerPath(preview, role)} />
        {own && onDraftChange && (
          <button
            type="button"
            onClick={() => onDraftChange(unsetAt(draft, path))}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title={`Inherit: take ${label} out of ${file.path}`}
            aria-label={`Inherit ${label}`}
          >
            <RotateCcw className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}

function layerPath(preview: ValuesPreview | undefined, role: string | undefined): string | undefined {
  if (!preview || !role) return undefined;
  if (role === "chart") {
    const { project, revision, path } = preview.chart;
    return project ? `${project} @ ${revision}: ${path === "." ? "" : `${path}/`}values.yaml` : undefined;
  }
  return preview.layers.find((l) => l.role === role)?.path;
}

const NUMBER = /^-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/;

/** An input that keeps the value's type: a switch for booleans, YAML for lists and maps. */
function ValueInput({
  value,
  label,
  onCommit,
}: {
  value: unknown;
  label: string;
  onCommit?: (next: unknown) => void;
}) {
  if (typeof value === "boolean") {
    return (
      <label className="flex items-center gap-2 py-1">
        <Switch size="sm" checked={value} disabled={!onCommit} onCheckedChange={(checked) => onCommit?.(checked)} aria-label={label} />
        <span className="font-mono text-muted-foreground">{String(value)}</span>
      </label>
    );
  }
  if (typeof value === "object" && value !== null) return <YamlValue value={value} label={label} onCommit={onCommit} />;
  return <TextValue value={value} label={label} onCommit={onCommit} />;
}

function display(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function TextValue({ value, label, onCommit }: { value: unknown; label: string; onCommit?: (next: unknown) => void }) {
  // The type the row started with: "1." on the way to "1.5" must not turn a number into a string.
  const [numeric] = useState(typeof value === "number");
  const parse = (text: string): unknown =>
    numeric && NUMBER.test(text.trim()) ? Number(text) : value === null && text === "" ? null : text;
  const [text, setText] = useState(() => display(value));
  const [last, setLast] = useState(value);
  if (!sameValues(value, last)) {
    setLast(value);
    if (!sameValues(parse(text), value)) setText(display(value));
  }
  return (
    <input
      type="text"
      aria-label={label}
      readOnly={!onCommit}
      value={text}
      placeholder={value === null ? "null" : undefined}
      onChange={(e) => {
        setText(e.target.value);
        onCommit?.(parse(e.target.value));
      }}
      className="w-full min-w-0 rounded bg-transparent px-1 py-1 font-mono transition-colors focus:bg-primary/5 focus:outline-none read-only:cursor-default"
    />
  );
}

function YamlValue({ value, label, onCommit }: { value: object; label: string; onCommit?: (next: unknown) => void }) {
  const dump = (v: unknown) => jsYaml.dump(v, { indent: 2, lineWidth: -1, noRefs: true, flowLevel: Array.isArray(v) && v.every((x) => !isMapping(x) && !Array.isArray(x)) ? 0 : -1 }).trimEnd();
  const [text, setText] = useState(() => dump(value));
  const [last, setLast] = useState<unknown>(value);
  const [error, setError] = useState("");
  if (!sameValues(value, last)) {
    setLast(value);
    setText(dump(value));
    setError("");
  }
  return (
    <div className="w-full space-y-0.5 py-0.5">
      <textarea
        aria-label={label}
        readOnly={!onCommit}
        value={text}
        rows={Math.min(8, text.split("\n").length)}
        spellCheck={false}
        onChange={(e) => {
          setText(e.target.value);
          try {
            const next = jsYaml.load(e.target.value);
            setError("");
            // Commit only what parses; keep `last` so the parsed value does not reformat the text.
            setLast(next);
            onCommit?.(next ?? null);
          } catch {
            setError("Invalid YAML");
          }
        }}
        className={cn(
          "w-full resize-y rounded bg-muted/30 px-2 py-1 font-mono text-[11px] leading-relaxed focus:bg-primary/5 focus:outline-none",
          error && "ring-1 ring-destructive/60",
        )}
      />
      {error && <p className="text-[10px] text-destructive">{error}</p>}
    </div>
  );
}
