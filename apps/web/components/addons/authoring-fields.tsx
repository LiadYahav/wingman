"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys, scopeLabel } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { parseIgnoreDifferences } from "@/lib/values";
import { Skeleton } from "@/components/ui/skeleton";
import type { AddonTemplate, FleetScope, ScopeReach } from "@/types/day2";

/** A chart folder becomes part of Application names: a DNS label (the service's rule `chart-name`). */
export const CHART_NAME = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;

/** A chart repo is `http(s)://...` (the service's rule `repourl-invalid`). */
export const REPO_URL = /^https?:\/\/\S+$/;

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  help,
  type = "text",
  list,
  mono = true,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  help?: React.ReactNode;
  type?: "text" | "url";
  list?: string;
  mono?: boolean;
  disabled?: boolean;
}) {
  return (
    <label className="block space-y-1 text-xs">
      <span className="font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        list={list}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        className={cn(
          "h-8 w-full rounded-lg border bg-background px-3 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60",
          mono && "font-mono",
        )}
      />
      {help && <span className="block text-muted-foreground">{help}</span>}
    </label>
  );
}

/** None, or one fleet scope with the destinations it reaches today. */
export function ScopeChoice({
  scopes,
  value,
  onChange,
  allowNone,
  unavailable = {},
  name,
}: {
  scopes: ScopeReach[];
  value: FleetScope | null;
  onChange: (scope: FleetScope | null) => void;
  allowNone: boolean;
  /** Scopes that cannot be chosen, with why. */
  unavailable?: Partial<Record<FleetScope, string>>;
  name: string;
}) {
  const options: { scope: FleetScope | null; label: string; detail: string; disabledBy?: string }[] = [
    ...(allowNone ? [{ scope: null, label: "No", detail: "only the team catalog: install it per cluster" }] : []),
    ...scopes.map((s) => ({
      scope: s.scope,
      label: s.label || scopeLabel(s.scope),
      detail: `${s.destinations.length} destination${s.destinations.length === 1 ? "" : "s"} today`,
      disabledBy: unavailable[s.scope],
    })),
  ];
  return (
    <div role="radiogroup" aria-label={name} className="grid gap-1.5 sm:grid-cols-2">
      {options.map((o) => {
        const checked = value === o.scope;
        return (
          <label
            key={o.scope ?? "none"}
            className={cn(
              "flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-xs transition-colors",
              checked ? "border-primary/50 bg-primary/5" : "hover:bg-muted/40",
              o.disabledBy && "cursor-not-allowed opacity-50",
            )}
          >
            <input
              type="radio"
              name={name}
              checked={checked}
              disabled={Boolean(o.disabledBy)}
              onChange={() => onChange(o.scope)}
              className="mt-0.5 accent-[var(--primary)]"
            />
            <span>
              <span className="block font-medium">{o.label}</span>
              <span className="block text-muted-foreground">{o.disabledBy ?? o.detail}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}

/** What a team's New operator form starts from, read from its own files (`GET /teams/{team}/addon-template`). */
export function useAddonTemplate(team: string, enabled = true) {
  return useQuery<AddonTemplate>({
    queryKey: day2Keys.addonTemplate(team),
    queryFn: () => api.get<AddonTemplate>(day2Api.addonTemplate(team)),
    enabled,
    staleTime: 60_000,
  });
}

export function TemplateSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" data-testid="template-loading">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

/**
 * ArgoCD's `ignoreDifferences` as YAML text: a list of objects, or empty for
 * none (`parseIgnoreDifferences` reads it; the form holds its submit while
 * it does not parse).
 */
export function IgnoreDifferencesField({
  path,
  text,
  onTextChange,
}: {
  path: string;
  text: string;
  onTextChange: (text: string) => void;
}) {
  const parsed = parseIgnoreDifferences(text);
  return (
    <div className="space-y-1">
      <p className="text-xs">
        <span className="font-semibold uppercase tracking-wide text-muted-foreground">ignoreDifferences</span>{" "}
        <code className="break-all rounded bg-muted px-1 py-px font-mono text-[11px]">{path}</code>
      </p>
      <textarea
        aria-label="ignoreDifferences"
        className={cn(
          "min-h-20 w-full resize-y rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/50",
          !parsed.ok && "border-destructive/60",
        )}
        rows={Math.min(14, Math.max(3, text.split("\n").length + 1))}
        value={text}
        placeholder={"# Empty: none.\n- group: apps\n  kind: Deployment\n  jsonPointers:\n  - /spec/replicas"}
        onChange={(e) => onTextChange(e.target.value)}
        spellCheck={false}
      />
      {parsed.ok ? (
        <p className="text-xs text-muted-foreground">ArgoCD&apos;s list, written as given. Empty removes the key.</p>
      ) : (
        <p className="text-xs text-destructive" role="alert">
          {parsed.error}
        </p>
      )}
    </div>
  );
}
