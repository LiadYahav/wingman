"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { DEFAULT_SYNC, day2Api, day2Keys, scopeLabel } from "@/lib/day2";
import { cn } from "@/lib/utils";
import type { Values } from "@/lib/values";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { AuthoringDialogs } from "@/components/addons/authoring-flow";
import { SyncOptionsControl } from "@/components/addons/sync-options";
import { YamlValuesField } from "@/components/addons/yaml-values-field";
import type { AddonTemplate, AuthoringChange, CreateAddonBody, FleetScope, ScopeReach, SyncSettings } from "@/types/day2";

/** A chart folder becomes part of Application names: a DNS label (the service's rule `chart-name`). */
const CHART_NAME = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  help,
  type = "text",
  list,
  mono = true,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  help?: React.ReactNode;
  type?: "text" | "url";
  list?: string;
  mono?: boolean;
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
        className={cn(
          "h-8 w-full rounded-lg border bg-background px-3 text-xs focus:outline-none focus:ring-2 focus:ring-primary/50",
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

export function useAddonTemplate(team: string, enabled: boolean) {
  return useQuery<AddonTemplate>({
    queryKey: day2Keys.addonTemplate(team),
    queryFn: () => api.get<AddonTemplate>(day2Api.addonTemplate(team)),
    enabled,
    staleTime: 60_000,
  });
}

function TemplateSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" data-testid="template-loading">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

/**
 * A new add-on in a team's catalog (ADR-0043): `operators/<name>/<name>.yaml`
 * and `values.yaml` in one MR, optionally a fleet default in the same MR. It
 * starts from the team's own files (`GET /teams/{team}/addon-template`).
 */
export function NewAddonDialog({
  team,
  open,
  onOpenChange,
  existing,
  readOnlyReason,
  onOpened,
}: {
  team: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The team's catalog names, which a new add-on cannot take. */
  existing: readonly string[];
  readOnlyReason: string | null;
  onOpened: (change: AuthoringChange) => void;
}) {
  const template = useAddonTemplate(team, open);
  const data = template.data;
  const [name, setName] = useState("");
  const [repourl, setRepourl] = useState<string | null>(null);
  const [revision, setRevision] = useState("");
  const [path, setPath] = useState("");
  const [namespace, setNamespace] = useState<string | null>(null);
  const [sync, setSync] = useState<SyncSettings | null>(null);
  const [values, setValues] = useState<Values | null>({});
  const [scope, setScope] = useState<FleetScope | null>(null);
  const [defaultValues, setDefaultValues] = useState<Values | null>({});

  const chart = name.trim();
  // Pre-filled while untouched: the team's usual chart-repo folder and the name as namespace.
  const repo = repourl ?? (data?.repourl_prefix && chart ? `${data.repourl_prefix}${chart}.git` : "");
  const ns = namespace ?? chart;
  const syncValue = sync ?? data?.sync ?? DEFAULT_SYNC;

  const blocker = !data
    ? "Loading the team's defaults"
    : !chart
      ? "Give the add-on a name"
      : !CHART_NAME.test(chart)
        ? "The name must be lowercase letters, digits and '-' (it becomes part of Application names)"
        : existing.includes(chart)
          ? `${team} has ${chart} in its catalog already`
          : !/^https?:\/\/\S+$/.test(repo.trim())
            ? "Give the chart repo URL (http or https)"
            : values === null || (scope !== null && defaultValues === null)
              ? "Fix the values YAML"
              : null;

  function body(): CreateAddonBody {
    const trimmedPath = path.trim();
    return {
      name: chart,
      repourl: repo.trim(),
      target_revision: revision.trim() || null,
      path: trimmedPath && trimmedPath !== "." ? trimmedPath : null,
      project_namespace: ns.trim() || null,
      sync: syncValue,
      ignore_differences: null,
      values: values ?? {},
      default_scope: scope,
      default_values: scope ? (defaultValues ?? {}) : {},
      // With a scope, the review fills in the clusters the user confirms (ADR-0043).
      ...(scope ? { confirm_changes: [] } : {}),
      message: null,
    };
  }

  return (
    <AuthoringDialogs
      open={open}
      onOpenChange={onOpenChange}
      title={`New add-on in ${team}`}
      description={`Adds operators/<name>/ to sigs/${team}: the add-on's team default, through one merge request. Clusters get it once it is installed on them or made a fleet default.`}
      blocker={blocker}
      readOnlyReason={readOnlyReason}
      body={body}
      method="post"
      url={(dryRun) => day2Api.createAddon(team, dryRun)}
      withConfirmations={scope !== null}
      onOpened={onOpened}
    >
      {template.error && !data ? (
        <ProblemList error={template.error} title={`${team}'s defaults for a new add-on could not be loaded`} />
      ) : !data ? (
        <TemplateSkeleton />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField
              label="Name"
              value={name}
              onChange={setName}
              placeholder="podinfo"
              help="The chart folder, operators/<name>/: lowercase letters, digits and '-'."
            />
            <TextField
              label="Project namespace"
              value={ns}
              onChange={setNamespace}
              placeholder="namespace"
              help="Where the chart is deployed on each cluster. Empty: none is set."
            />
          </div>
          <TextField
            label="Chart repo URL (repourl)"
            type="url"
            value={repo}
            onChange={setRepourl}
            placeholder={data.repourl_prefix ? `${data.repourl_prefix}<name>.git` : "https://gitlab.example.com/helm-charts/<name>.git"}
            help={
              <>
                Written as lowercase <code>repourl</code>, the only spelling the platform reads.
              </>
            }
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField
              label="Revision (targetRevision)"
              value={revision}
              onChange={setRevision}
              placeholder="HEAD"
              help="A branch of the chart repo. Empty: HEAD, the repo's default branch."
            />
            <TextField label="Path" value={path} onChange={setPath} placeholder="." help="The chart's folder in its repo. Empty: the root." />
          </div>
          <SyncOptionsControl value={syncValue} onChange={setSync} known={data.known_sync_options} hint={data.sync_source} />
          <YamlValuesField
            label="Team values"
            path={`operators/${chart || "<name>"}/values.yaml`}
            initial={{}}
            onChange={setValues}
          />
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Also make it a default for</p>
            <ScopeChoice scopes={data.scopes} value={scope} onChange={setScope} allowNone name="Fleet default" />
            {scope && (
              <YamlValuesField
                label="Fleet default values"
                path={`defaults/${scope}/${chart || "<name>"}/values.yaml`}
                initial={{}}
                onChange={setDefaultValues}
                placeholder="# Empty: the team values apply on every destination."
              />
            )}
          </div>
        </>
      )}
    </AuthoringDialogs>
  );
}
