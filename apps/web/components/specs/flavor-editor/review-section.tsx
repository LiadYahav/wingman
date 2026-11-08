"use client";

import { useEffect, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { FileCode2, Info, Loader2, Lock } from "lucide-react";
import { api, isApiError } from "@/lib/api-client";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProblemList } from "@/components/common/problem-list";
import { cn } from "@/lib/utils";
import type { ClusterPreview, ClusterSpec, Mce, OpenShiftVersions, TemplateField } from "@/types";
import { inputCls } from "./controls";
import { pathLabel, previewPlan, previewRelease, sampleClusterName, type FlavorDraft, type ValueLine } from "./model";

const codeCls =
  "max-h-[32rem] overflow-auto rounded-lg border bg-muted/40 p-4 font-mono text-xs leading-5 text-foreground/90 dark:bg-black/30";

/** `value` once it has stopped changing for `ms`. */
function useSettled<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

/** Whether `ref`'s element has been on screen (once seen, it stays true). */
function useSeen(ref: React.RefObject<HTMLElement | null>): boolean {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === "undefined") {
      const timer = setTimeout(() => setSeen(true), 0);
      return () => clearTimeout(timer);
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setSeen(true);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, seen]);
  return seen;
}

function ValueList({ title, icon, lines, empty, testId }: { title: string; icon?: React.ReactNode; lines: ValueLine[]; empty: string; testId: string }) {
  return (
    <div className="min-w-0" data-testid={testId}>
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        {icon}
        {title}
        <span className="font-normal text-muted-foreground tabular">{lines.length}</span>
      </h3>
      {lines.length === 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">{empty}</p>
      ) : (
        <dl className="mt-2 divide-y divide-border/60">
          {lines.map((line) => (
            <div key={line.path} className="flex items-baseline justify-between gap-4 py-1.5">
              <dt className="shrink-0 text-xs text-muted-foreground">{line.label}</dt>
              <dd className="min-w-0 text-right font-mono text-xs break-words">
                {line.value}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

/**
 * The cluster file a saved flavor gives, rendered by day1 (`POST
 * /clusters/preview`) with this page's values, on an MCE and release the
 * person picks. Day1 renders only a flavor that is in the specs repo, so a
 * new flavor has no preview until its MR merges.
 */
function ClusterFilePreview({
  draft,
  saved,
  schema,
}: {
  draft: FlavorDraft;
  /** The flavor as saved; `null` for a new one. */
  saved: ClusterSpec | null;
  schema: TemplateField[] | undefined;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useSeen(ref);
  const [mceChoice, setMceChoice] = useState<string | null>(null);
  const [versionChoice, setVersionChoice] = useState<string | null>(null);
  const [nameChoice, setNameChoice] = useState<string | null>(null);

  const { data: mces = [], error: mcesError } = useQuery<Mce[]>({
    queryKey: ["mces", "all"],
    queryFn: () => api.get<Mce[]>("/api/day1/mces"),
    staleTime: 60_000,
    enabled: Boolean(saved) && seen,
  });
  const usable = mces.filter((m) => m.follows_convention && m.env);
  const mce = usable.find((m) => m.name === mceChoice) ?? usable[0];
  const { data: offered, error: versionsError } = useQuery<OpenShiftVersions>({
    queryKey: ["mce-openshift-versions", mce?.name],
    queryFn: () => api.get<OpenShiftVersions>(`/api/day1/mces/${encodeURIComponent(mce!.name)}/openshift-versions`),
    staleTime: 60_000,
    enabled: Boolean(saved && mce) && seen,
  });
  const versions = offered?.versions ?? [];
  const version =
    versionChoice && versions.includes(versionChoice)
      ? versionChoice
      : previewRelease(draft.values.openshift_release_version, mce, versions);
  const clusterName = nameChoice ?? (mce ? sampleClusterName(mce) : "");

  const plan =
    saved && schema && mce && version && clusterName
      ? previewPlan({ draft, saved, schema, mce, openshiftVersion: version, clusterName })
      : null;
  const body = useSettled(plan ? JSON.stringify(plan.request) : "", 600);
  const preview = useQuery<ClusterPreview>({
    queryKey: ["flavor-cluster-preview", body],
    queryFn: () => api.post<ClusterPreview>("/api/day1/clusters/preview", JSON.parse(body)),
    enabled: Boolean(body) && seen,
    retry: false,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  if (!saved) {
    return (
      <div ref={ref} className="flex items-start gap-3 rounded-xl border border-dashed p-5" data-testid="cluster-preview-unavailable">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="space-y-1 text-sm">
          <p className="font-medium">The cluster file can be previewed once this flavor is saved</p>
          <p className="text-muted-foreground">
            Day1 renders a cluster file only from a flavor in the specs repo. When this flavor&apos;s merge request is merged,
            its edit page previews the file it gives, live, as you change it.
          </p>
        </div>
      </div>
    );
  }

  const mceOptions: ComboboxOption[] = usable.map((m) => ({ value: m.name, label: m.name, description: m.site }));
  const versionOptions: ComboboxOption[] = versions.map((v) => ({ value: v, label: v }));
  const sourceError = mcesError ?? versionsError;
  const updating = preview.isFetching || (plan !== null && body !== JSON.stringify(plan.request));

  return (
    <div ref={ref} className="space-y-3" data-testid="cluster-preview">
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-0 space-y-1">
          <span className="block text-xs text-muted-foreground">MCE</span>
          <Combobox
            className="w-60"
            options={mceOptions}
            value={mce?.name ?? null}
            onValueChange={(v) => {
              setMceChoice(v);
              setNameChoice(null);
            }}
            placeholder={mces.length === 0 ? "Loading MCEs…" : "Choose an MCE…"}
            searchPlaceholder="Search MCEs…"
            emptyMessage="No MCE matches."
            aria-label="Preview MCE"
          />
        </label>
        <label className="min-w-0 space-y-1">
          <span className="block text-xs text-muted-foreground">OpenShift</span>
          <Combobox
            className="w-36"
            options={versionOptions}
            value={version}
            onValueChange={setVersionChoice}
            placeholder={mce && !offered ? "Loading…" : "Release…"}
            searchPlaceholder="Search releases…"
            emptyMessage="No release matches."
            aria-label="Preview OpenShift release"
          />
        </label>
        <label className="min-w-0 flex-1 space-y-1">
          <span className="block text-xs text-muted-foreground">Example cluster name</span>
          <input
            className={cn(inputCls, "h-8 font-mono text-xs")}
            value={clusterName}
            onChange={(e) => setNameChoice(e.target.value.trim())}
            aria-label="Preview cluster name"
            spellCheck={false}
          />
        </label>
        <span className="flex h-8 items-center text-xs text-muted-foreground" role="status" aria-live="polite">
          {updating ? (
            <>
              <Loader2 className="mr-1 h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden /> Rendering…
            </>
          ) : preview.data ? (
            "Up to date"
          ) : null}
        </span>
      </div>

      {sourceError ? (
        <ProblemList error={sourceError} title="The MCEs or their OpenShift releases could not be read" />
      ) : usable.length === 0 && mces.length > 0 ? (
        <p className="text-sm text-muted-foreground">No MCE follows the naming convention, so there is nowhere to preview a cluster.</p>
      ) : null}

      {preview.error && !preview.isFetching ? (
        <ProblemList
          error={preview.error}
          title={
            isApiError(preview.error, "REVISION_CONFLICT")
              ? "The saved flavor changed since you opened it: reload the flavor to preview it"
              : "Day1 could not render the cluster file"
          }
        />
      ) : preview.data ? (
        <div className={cn("transition-opacity duration-200", updating && "opacity-60")}>
          <p className="mb-1.5 truncate font-mono text-[11px] text-muted-foreground" title={preview.data.path}>
            {preview.data.path}
          </p>
          <pre className={codeCls} data-testid="cluster-preview-yaml">
            {preview.data.yaml}
          </pre>
        </div>
      ) : (
        <div className="h-40 animate-pulse rounded-lg bg-muted/50 motion-reduce:animate-none" aria-hidden />
      )}

      {plan && (
        <ul className="space-y-1 text-xs text-muted-foreground">
          <li>
            Rendered by day1 from the saved flavor <span className="font-mono">v{saved.metadata.version}</span> with this page&apos;s
            values. Nothing is written.
          </li>
          {plan.samples.length > 0 && (
            <li data-testid="preview-samples">
              Each cluster sets {plan.samples.map(pathLabel).join(", ")}; the preview fills in examples.
            </li>
          )}
          {plan.asSaved.length > 0 && (
            <li className="text-status-warning-fg" data-testid="preview-as-saved">
              Shown as saved until this change merges (day1 enforces the saved locks): {plan.asSaved.map(pathLabel).join(", ")}.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

/**
 * Part 4: what every cluster gets (the locked values and the presets), the
 * flavor file a save proposes, the cluster file it gives, and the shared
 * template for reference.
 */
export function ReviewSection({
  draft,
  name,
  yaml,
  saved,
  schema,
  template,
  lines,
}: {
  draft: FlavorDraft;
  name: string;
  /** The flavor file a save proposes. */
  yaml: string;
  saved: ClusterSpec | null;
  schema: TemplateField[] | undefined;
  template: string;
  lines: { locked: ValueLine[]; presets: ValueLine[] };
}) {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        <ValueList
          title="Locked"
          icon={<Lock className="h-3.5 w-3.5 text-primary" aria-hidden />}
          lines={lines.locked}
          empty="Nothing is locked: a cluster may change every value."
          testId="review-locked"
        />
        <ValueList title="Presets" lines={lines.presets} empty="No presets: each cluster fills in every value." testId="review-presets" />
      </div>

      <Tabs defaultValue={saved ? "cluster" : "flavor"}>
        <TabsList>
          <TabsTrigger value="cluster">Cluster file</TabsTrigger>
          <TabsTrigger value="flavor">Flavor file</TabsTrigger>
          <TabsTrigger value="template">Template</TabsTrigger>
        </TabsList>
        <TabsContent value="cluster" keepMounted className="pt-2">
          <ClusterFilePreview draft={draft} saved={saved} schema={schema} />
        </TabsContent>
        <TabsContent value="flavor" className="space-y-1.5 pt-2">
          <p className="truncate font-mono text-[11px] text-muted-foreground">
            specs/{name || "<name>"}.yaml
          </p>
          <pre className={codeCls} data-testid="flavor-yaml">
            {yaml}
          </pre>
        </TabsContent>
        <TabsContent value="template" className="space-y-1.5 pt-2">
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <FileCode2 className="h-3 w-3" aria-hidden />
            <span className="font-mono">cluster-template.j2</span> · shared by every flavor
          </p>
          <pre className={codeCls}>{template || "The specs repo has no cluster-template.j2."}</pre>
        </TabsContent>
      </Tabs>
    </div>
  );
}
