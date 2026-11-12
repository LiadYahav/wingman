"use client";

import { useId, useState } from "react";
import { Plus, X } from "lucide-react";
import { SYNC_OPTION_PATTERN } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import type { SyncSettings } from "@/types/day2";

/**
 * The leaf app's ArgoCD sync options (ADR-0043): auto-sync, and with it prune
 * and self-heal, and the `syncOptions` list. Prune and self-heal exist only
 * with auto-sync, so turning auto-sync off clears them. Options keep their
 * order; a known option is a checkbox, any other `Name=value` can be added.
 */
export function SyncOptionsControl({
  value,
  onChange,
  known,
  hint,
  disabled = false,
}: {
  value: SyncSettings;
  onChange: (next: SyncSettings) => void;
  /** The template's `known_sync_options`. */
  known: readonly string[];
  /** Where the starting settings come from (the template's `sync_source`). */
  hint?: string;
  disabled?: boolean;
}) {
  const id = useId();
  const [custom, setCustom] = useState("");
  const [customError, setCustomError] = useState("");
  const extra = value.sync_options.filter((o) => !known.includes(o));

  function setAuto(auto: boolean) {
    onChange(auto ? { ...value, auto_sync: true } : { ...value, auto_sync: false, prune: false, self_heal: false });
  }

  function toggle(option: string, on: boolean) {
    const without = value.sync_options.filter((o) => o !== option);
    onChange({ ...value, sync_options: on ? [...without, option] : without });
  }

  function addCustom() {
    const option = custom.trim();
    if (!SYNC_OPTION_PATTERN.test(option)) {
      setCustomError("An option is Name=value, e.g. ServerSideApply=true.");
      return;
    }
    if (value.sync_options.includes(option)) {
      setCustomError(`${option} is already on the list.`);
      return;
    }
    onChange({ ...value, sync_options: [...value.sync_options, option] });
    setCustom("");
    setCustomError("");
  }

  return (
    <fieldset className="space-y-3 rounded-lg border p-3" disabled={disabled} aria-label="Sync options">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sync options</legend>
      <div className="flex items-start gap-3">
        <Switch
          id={`${id}-auto`}
          checked={value.auto_sync}
          onCheckedChange={(checked) => setAuto(Boolean(checked))}
          disabled={disabled}
          aria-label="Auto-sync"
          className="mt-0.5"
        />
        <label htmlFor={`${id}-auto`} className="min-w-0 space-y-0.5 text-xs">
          <span className="block font-medium text-foreground">Auto-sync</span>
          <span className="block text-muted-foreground" data-testid="sync-mode-note">
            {value.auto_sync
              ? "ArgoCD syncs the app by itself once the merge request is merged."
              : "Manual sync: nothing deploys after the merge until someone syncs the app in ArgoCD (Wingman has no ArgoCD access)."}
          </span>
        </label>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2 pl-1 text-xs">
        {(
          [
            ["prune", "Prune", "Delete resources the chart no longer renders"],
            ["self_heal", "Self-heal", "Undo changes made on the cluster outside Git"],
          ] as const
        ).map(([key, label, description]) => (
          <label
            key={key}
            className={cn("flex items-start gap-2", !value.auto_sync && "cursor-not-allowed opacity-50")}
            title={value.auto_sync ? description : "Only with auto-sync"}
          >
            <Checkbox
              checked={value[key]}
              onCheckedChange={(checked) => onChange({ ...value, [key]: checked })}
              disabled={disabled || !value.auto_sync}
              className="mt-px"
            />
            <span>
              <span className="font-medium">{label}</span>
              <span className="block text-muted-foreground">{value.auto_sync ? description : "only with auto-sync"}</span>
            </span>
          </label>
        ))}
      </div>
      <div className="space-y-1.5">
        <p className="text-xs font-medium">syncOptions</p>
        <ul className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
          {known.map((option) => (
            <li key={option}>
              <label className="flex items-center gap-2 font-mono text-[11px]">
                <Checkbox
                  checked={value.sync_options.includes(option)}
                  onCheckedChange={(checked) => toggle(option, checked)}
                  disabled={disabled}
                />
                {option}
              </label>
            </li>
          ))}
        </ul>
        {extra.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Other sync options">
            {extra.map((option) => (
              <li key={option} className="inline-flex items-center gap-1 rounded-md border bg-card px-2 py-0.5 font-mono text-[11px]">
                {option}
                <button
                  type="button"
                  onClick={() => toggle(option, false)}
                  disabled={disabled}
                  aria-label={`Remove ${option}`}
                  className="rounded text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={custom}
            onChange={(e) => {
              setCustom(e.target.value);
              setCustomError("");
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustom();
              }
            }}
            disabled={disabled}
            placeholder="Another option, Name=value"
            aria-label="Another sync option"
            className="h-7 min-w-0 flex-1 rounded-lg border bg-background px-2.5 font-mono text-[11px] focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          <button
            type="button"
            onClick={addCustom}
            disabled={disabled || !custom.trim()}
            className="inline-flex h-7 items-center gap-1 rounded-lg border px-2.5 text-xs font-medium transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-3 w-3" />
            Add
          </button>
        </div>
        {customError && (
          <p className="text-xs text-destructive" role="alert">
            {customError}
          </p>
        )}
      </div>
      {hint && <p className="text-[11px] text-muted-foreground">Pre-filled from {hint}.</p>}
    </fieldset>
  );
}
