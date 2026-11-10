"use client";

import { useState } from "react";
import jsYaml from "js-yaml";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { isMapping } from "@/lib/values";
import { cn } from "@/lib/utils";
import { inputCls, ValueField } from "./controls";
import { inputLabel, type OtherInput } from "./model";

const LABEL_KEY = /^[A-Za-z0-9_./-]+$/;

interface Row {
  id: number;
  key: string;
  value: string;
}

function rowsOf(value: unknown): Row[] {
  if (!isMapping(value)) return [];
  return Object.entries(value).map(([key, v], id) => ({ id, key, value: typeof v === "string" ? v : JSON.stringify(v) }));
}

/** Why a row would not be saved as typed; `null` when it is fine. */
function rowProblem(row: Row, rows: Row[]): string | null {
  if (!row.key) return row.value ? "Give it a key; until then it is not saved" : null;
  if (!LABEL_KEY.test(row.key)) return "A key is letters, digits, '_', '.', '/' or '-'";
  if (rows.find((r) => r.key === row.key)!.id !== row.id) return "This key is used above; only the first is saved";
  return null;
}

/**
 * A nodepool's `node_labels` as key/value rows. A row without a key is kept
 * while it is typed and saved once it has one; an empty map is "none".
 */
export function NodeLabelsEditor({
  value,
  onChange,
  label,
  id,
  describedBy,
  invalid,
}: {
  value: unknown;
  /** The map to save; `undefined` when there are no labels. */
  onChange: (labels: Record<string, string> | undefined) => void;
  label: string;
  id: string;
  describedBy: string;
  invalid: boolean;
}) {
  const [rows, setRows] = useState<Row[]>(() => rowsOf(value));
  const update = (next: Row[]) => {
    setRows(next);
    const map: Record<string, string> = {};
    for (const row of next) {
      if (row.key && LABEL_KEY.test(row.key) && !(row.key in map)) map[row.key] = row.value;
    }
    onChange(Object.keys(map).length > 0 ? map : undefined);
  };
  const nextId = () => Math.max(-1, ...rows.map((r) => r.id)) + 1;

  return (
    <div className="space-y-2" id={id} aria-describedby={describedBy}>
      {rows.length === 0 && <p className="text-xs text-muted-foreground">No node labels.</p>}
      {rows.length > 0 && (
        <ul className="space-y-1.5" aria-label={label}>
          {rows.map((row, index) => {
            const problem = rowProblem(row, rows);
            return (
              <li key={row.id} className="space-y-1">
                <div className="flex items-center gap-1.5">
                  <input
                    className={cn(inputCls, "h-8 flex-1 font-mono text-xs")}
                    placeholder="key"
                    aria-label={`${label}: key ${index + 1}`}
                    aria-invalid={Boolean(problem) || invalid}
                    value={row.key}
                    onChange={(e) => update(rows.map((r) => (r.id === row.id ? { ...r, key: e.target.value.trim() } : r)))}
                  />
                  <span aria-hidden className="text-muted-foreground">=</span>
                  <input
                    className={cn(inputCls, "h-8 flex-1 font-mono text-xs")}
                    placeholder="value"
                    aria-label={`${label}: value ${index + 1}`}
                    value={row.value}
                    onChange={(e) => update(rows.map((r) => (r.id === row.id ? { ...r, value: e.target.value } : r)))}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove ${row.key || "label"} (label ${index + 1})`}
                    onClick={() => update(rows.filter((r) => r.id !== row.id))}
                  >
                    <X />
                  </Button>
                </div>
                {problem && <p className="pl-1 text-xs text-status-warning-fg">{problem}</p>}
              </li>
            );
          })}
        </ul>
      )}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        onClick={() => setRows([...rows, { id: nextId(), key: "", value: "" }])}
      >
        <Plus /> Add label
      </Button>
    </div>
  );
}

/** A text the person typed for an `object` or `list` input, parsed as YAML. */
function parseStructured(text: string): { ok: true; value: unknown } | { ok: false; error: string } {
  if (!text.trim()) return { ok: true, value: undefined };
  try {
    return { ok: true, value: jsYaml.load(text) };
  } catch (e) {
    return { ok: false, error: e instanceof jsYaml.YAMLException ? `Not valid YAML: ${e.reason}` : "Not valid YAML" };
  }
}

function StructuredInput({
  value,
  onChange,
  id,
  describedBy,
  invalid,
  placeholder,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  id: string;
  describedBy: string;
  invalid: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState(() => (value === undefined ? "" : jsYaml.dump(value, { lineWidth: 120 }).trimEnd()));
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="space-y-1">
      <textarea
        id={id}
        aria-describedby={describedBy}
        aria-invalid={invalid || Boolean(error)}
        rows={3}
        className={cn(inputCls, "h-auto resize-y py-2 font-mono text-xs")}
        placeholder={placeholder ?? "YAML"}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          const parsed = parseStructured(e.target.value);
          if (parsed.ok) {
            setError(null);
            onChange(parsed.value);
          } else setError(parsed.error);
        }}
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

/**
 * A template input the flavor may preset but never lock (§6): text, a
 * number, a switch, or YAML for a list or map. Empty means not set.
 */
export function PresetInput({
  input,
  path,
  value,
  onChange,
  problems,
}: {
  input: OtherInput;
  path: string;
  value: unknown;
  onChange: (value: unknown) => void;
  problems?: string[];
}) {
  const empty = value === undefined || value === "";
  const hint = input.unread
    ? "The template does not read this input; it is kept as the flavor sets it."
    : input.name === "openshift_release_version"
      ? "The create form's default; each cluster picks a release its MCE offers."
      : undefined;
  return (
    <ValueField path={path} label={inputLabel(input.name)} empty={empty} problems={problems} hint={hint}>
      {({ inputId, describedBy, invalid }) => {
        if (input.type === "boolean") {
          return (
            <div className="flex h-9 items-center gap-2">
              <Switch
                id={inputId}
                aria-describedby={describedBy}
                checked={value === true}
                onCheckedChange={(checked) => onChange(checked ? true : undefined)}
              />
              <span className="text-sm text-muted-foreground">{value === true ? "On" : "Off"}</span>
            </div>
          );
        }
        if (input.type === "list" || input.type === "object") {
          return (
            <StructuredInput
              id={inputId}
              describedBy={describedBy}
              invalid={invalid}
              value={value}
              onChange={onChange}
              placeholder={input.example ? `e.g. ${input.example}` : undefined}
            />
          );
        }
        return (
          <input
            id={inputId}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            className={cn(inputCls, "font-mono text-[13px]")}
            inputMode={input.type === "integer" ? "numeric" : undefined}
            placeholder={input.example ? `e.g. ${input.example}` : "Not set"}
            value={value === undefined ? "" : String(value)}
            onChange={(e) => {
              const text = e.target.value;
              if (!text) return onChange(undefined);
              onChange(input.type === "integer" && /^-?\d+$/.test(text) ? Number(text) : text);
            }}
          />
        );
      }}
    </ValueField>
  );
}
