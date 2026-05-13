"use client";

import { useState, useMemo } from "react";
import { Package } from "lucide-react";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { OverrideableField } from "@/types";

// ── Helper Functions ──────────────────────────────────────────────────────────

export type FieldType = "string" | "integer" | "boolean" | "object" | "array";

export function deepMergeValues(
  base: Record<string, unknown>,
  override: Record<string, unknown>
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  for (const [key, val] of Object.entries(override)) {
    const baseVal = result[key];
    if (
      val !== null && typeof val === "object" && !Array.isArray(val) &&
      baseVal !== null && typeof baseVal === "object" && !Array.isArray(baseVal)
    ) {
      result[key] = deepMergeValues(
        baseVal as Record<string, unknown>,
        val as Record<string, unknown>
      );
    } else {
      result[key] = val;
    }
  }
  return result;
}

export function flattenKeys(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const key of Object.keys(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    const value = obj[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      keys.push(...flattenKeys(value as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys;
}

export function inferFieldType(value: unknown): FieldType {
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number" && Number.isInteger(value)) return "integer";
  if (Array.isArray(value)) return "array";
  if (value && typeof value === "object") return "object";
  return "string";
}

export function getValueAtPath(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current && typeof current === "object" && part in current) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}

function formatValueSummary(value: unknown, type: FieldType): { summary: string; detail?: string } {
  if (value === null || value === undefined) return { summary: "null" };

  if (type === "array" && Array.isArray(value)) {
    const count = value.length;
    if (count === 0) return { summary: "Empty array" };
    const firstItem = value[0];
    if (typeof firstItem === "object" && firstItem !== null) {
      const keys = Object.keys(firstItem);
      const keyPreview = keys.slice(0, 3).join(", ");
      return {
        summary: `${count} item${count > 1 ? "s" : ""}`,
        detail: keys.length > 3 ? `Fields: ${keyPreview}, ...` : `Fields: ${keyPreview}`
      };
    }
    return { summary: `${count} item${count > 1 ? "s" : ""}` };
  }

  if (type === "object" && typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>);
    if (keys.length === 0) return { summary: "Empty object" };
    const keyPreview = keys.slice(0, 4).join(", ");
    return {
      summary: `${keys.length} propert${keys.length > 1 ? "ies" : "y"}`,
      detail: keys.length > 4 ? `${keyPreview}, ...` : keyPreview
    };
  }

  if (type === "boolean") {
    return { summary: value ? "true" : "false" };
  }

  if (type === "integer" || type === "string") {
    const str = String(value);
    if (str.length > 50) {
      return { summary: `"${str.substring(0, 47)}..."` };
    }
    return { summary: type === "string" ? `"${str}"` : str };
  }

  return { summary: String(value) };
}

function getTypeBadgeColor(type: FieldType): string {
  switch (type) {
    case "string": return "bg-blue-500/10 text-blue-600 dark:text-blue-400";
    case "integer": return "bg-amber-500/10 text-amber-600 dark:text-amber-400";
    case "boolean": return "bg-green-500/10 text-green-600 dark:text-green-400";
    case "array": return "bg-purple-500/10 text-purple-600 dark:text-purple-400";
    case "object": return "bg-pink-500/10 text-pink-600 dark:text-pink-400";
    default: return "bg-muted text-muted-foreground";
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

interface ConfigureOverrideableDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  addonName: string;
  defaultValues: Record<string, unknown>;
  currentOverrideable: OverrideableField[];
  onSave: (fields: OverrideableField[]) => void;
  isLoadingValues?: boolean;
}

export function ConfigureOverrideableDialog({
  open,
  onOpenChange,
  addonName,
  defaultValues,
  currentOverrideable,
  onSave,
  isLoadingValues = false,
}: ConfigureOverrideableDialogProps) {
  const availablePaths = useMemo(
    () => flattenKeys(defaultValues),
    [defaultValues]
  );

  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(() =>
    new Set(currentOverrideable.map((f) => f.path))
  );
  const [fieldMeta, setFieldMeta] = useState<
    Record<string, { type: FieldType; description: string }>
  >(() => {
    const meta: Record<string, { type: FieldType; description: string }> = {};
    for (const f of currentOverrideable) {
      const value = getValueAtPath(defaultValues, f.path);
      const inferredType = inferFieldType(value);
      // Correct legacy data: arrays/objects should use inferred type
      const correctedType = (inferredType === "array" || inferredType === "object") ? inferredType : f.type;
      meta[f.path] = { type: correctedType, description: f.description ?? "" };
    }
    return meta;
  });

  const togglePath = (path: string) => {
    const newSet = new Set(selectedPaths);
    if (newSet.has(path)) {
      newSet.delete(path);
    } else {
      newSet.add(path);
      if (!fieldMeta[path]) {
        const value = getValueAtPath(defaultValues, path);
        setFieldMeta((m) => ({
          ...m,
          [path]: { type: inferFieldType(value), description: "" },
        }));
      }
    }
    setSelectedPaths(newSet);
  };

  const updateMeta = (
    path: string,
    updates: Partial<{ type: FieldType; description: string }>
  ) => {
    setFieldMeta((m) => ({
      ...m,
      [path]: { ...m[path], ...updates },
    }));
  };

  const handleSave = () => {
    const fields: OverrideableField[] = Array.from(selectedPaths).map((path) => ({
      path,
      type: fieldMeta[path]?.type ?? "string",
      default: getValueAtPath(defaultValues, path),
      description: fieldMeta[path]?.description ?? "",
    }));
    onSave(fields);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!max-w-[95vw] !w-[95vw] !max-h-[90vh] !h-[85vh] flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b bg-muted/30">
          <DialogTitle className="text-xl font-bold">Configure Overrideable Fields</DialogTitle>
          <DialogDescription className="text-sm mt-1">
            Select fields from <span className="font-semibold text-foreground">{addonName}</span> that cluster creators can customize.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {isLoadingValues ? (
            <div className="flex flex-col items-center justify-center py-16 text-center" data-testid="loading-values-message">
              <div className="rounded-full bg-muted p-4 mb-4 animate-pulse">
                <Package className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">Loading chart values…</p>
              <p className="text-xs text-muted-foreground mt-1">Fetching helm chart defaults</p>
            </div>
          ) : availablePaths.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center" data-testid="no-fields-message">
              <div className="rounded-full bg-muted p-4 mb-4">
                <Package className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">No fields available</p>
              <p className="text-xs text-muted-foreground mt-1">
                This addon has no default values defined.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {availablePaths.map((path) => {
                const isSelected = selectedPaths.has(path);
                const value = getValueAtPath(defaultValues, path);
                const detectedType = inferFieldType(value);
                const currentType = fieldMeta[path]?.type ?? detectedType;
                const valueSummary = formatValueSummary(value, detectedType);

                return (
                  <div
                    key={path}
                    data-testid={`field-row-${path.replace(/\./g, "-")}`}
                    className={cn(
                      "rounded-lg border transition-all",
                      isSelected
                        ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                        : "border-border hover:border-primary/40 hover:bg-muted/20"
                    )}
                  >
                    <div
                      className="flex items-center gap-4 p-4 cursor-pointer"
                      onClick={() => togglePath(path)}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => togglePath(path)}
                        onClick={(e) => e.stopPropagation()}
                        className="h-4 w-4 rounded border-2 border-muted-foreground/40 text-primary focus:ring-primary shrink-0"
                        data-testid={`field-checkbox-${path.replace(/\./g, "-")}`}
                      />

                      <div className="flex-1 min-w-0 flex items-center gap-3">
                        <code className="text-sm font-semibold text-foreground truncate">{path}</code>
                        <span className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase shrink-0",
                          getTypeBadgeColor(detectedType)
                        )}>
                          {detectedType}
                        </span>
                      </div>

                      <div className="text-right shrink-0 text-sm text-muted-foreground">
                        <span className="font-mono">{valueSummary.summary}</span>
                        {valueSummary.detail && (
                          <p className="text-xs text-muted-foreground/70 mt-0.5">{valueSummary.detail}</p>
                        )}
                      </div>
                    </div>

                    {isSelected && (
                      <div
                        className="px-4 pb-4 pt-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="rounded-lg bg-muted/40 p-4 space-y-4">
                          <div className="grid sm:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="text-xs font-medium text-muted-foreground">
                                Input Type
                              </label>
                              <Select
                                value={currentType}
                                onValueChange={(v) => updateMeta(path, { type: v as FieldType })}
                              >
                                <SelectTrigger className="h-9 bg-background" data-testid={`field-type-${path.replace(/\./g, "-")}`}>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent alignItemWithTrigger={false}>
                                  <SelectItem value="string">Text input</SelectItem>
                                  <SelectItem value="integer">Number input</SelectItem>
                                  <SelectItem value="boolean">Checkbox</SelectItem>
                                  <SelectItem value="array">Array editor</SelectItem>
                                  <SelectItem value="object">Object editor</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1.5">
                              <label className="text-xs font-medium text-muted-foreground">
                                Help Text
                              </label>
                              <input
                                type="text"
                                value={fieldMeta[path]?.description ?? ""}
                                onChange={(e) => updateMeta(path, { description: e.target.value })}
                                placeholder="Brief description for cluster creators..."
                                className="w-full h-9 rounded-lg border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                data-testid={`field-help-${path.replace(/\./g, "-")}`}
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <DialogFooter className="px-6 py-4 border-t bg-muted/20 gap-3 sm:gap-2">
          <div className="flex-1 text-sm text-muted-foreground" data-testid="selected-count">
            <span className="font-semibold text-foreground">{selectedPaths.size}</span> field{selectedPaths.size !== 1 ? "s" : ""} will be overrideable
          </div>
          <button
            onClick={() => onOpenChange(false)}
            className={buttonVariants({ variant: "outline" })}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className={buttonVariants()}
            data-testid="save-config-button"
          >
            Save Configuration
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
