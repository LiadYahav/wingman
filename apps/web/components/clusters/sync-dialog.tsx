"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Network, Package, RotateCcw, RotateCw, TriangleAlert } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Combobox, type ComboboxOption } from "@/components/ui/combobox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { MRCreationProgress } from "@/components/common/mr-creation-progress";
import { ProblemList } from "@/components/common/problem-list";
import { YamlDiffViewer } from "@/components/common/yaml-diff-viewer";
import { api, isApiError } from "@/lib/api-client";
import { defaultHardware, hardwareOptions as hardwareOptionsOf, useMachineConfigs } from "@/lib/machine-configs";
import { toastMrOpened } from "@/lib/mr-toast";
import { writeErrorTitle } from "@/lib/write-errors";
import { cn } from "@/lib/utils";
import type {
  AddonDrift, ConfigRemoval, HardwareChoice, MRDetail, NodepoolRef, Rebooting, SyncPreview, SyncPreviewRequest, SyncRequest,
} from "@/types";

/** A nodepool whose network hardware a person chooses, and what they chose. */
interface Choice {
  nodepool: NodepoolRef;
  /** Why it needs a choice, from the preview that asked for it. */
  reason: string | null;
  hardware: string;
}

const removalKey = (r: ConfigRemoval) => `${r.nodepool.index}\u0000${r.name}`;

function Section({
  title,
  icon: Icon,
  tone = "neutral",
  children,
  testId,
}: {
  title: string;
  icon?: typeof Network;
  tone?: "neutral" | "warning";
  children: React.ReactNode;
  testId: string;
}) {
  return (
    <section
      data-testid={testId}
      aria-label={title}
      className={cn(
        "rounded-lg border p-3.5 space-y-2",
        tone === "warning" ? "border-status-warning/30 bg-status-warning/5" : "bg-muted/20"
      )}
    >
      <h3
        className={cn(
          "flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide",
          tone === "warning" ? "text-status-warning-fg" : "text-muted-foreground"
        )}
      >
        {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
        {title}
      </h3>
      {children}
    </section>
  );
}

/** `2 nodes`, `25% of the nodes`: an `inPlace.maxUnavailable` as a count. */
function atATime(maxUnavailable: number | string): string {
  const n = typeof maxUnavailable === "number" ? maxUnavailable : /^\d+$/.test(maxUnavailable) ? Number(maxUnavailable) : null;
  if (n !== null) return `${n} node${n === 1 ? "" : "s"}`;
  return `${maxUnavailable} of the nodes`;
}

/**
 * How merging a sync rolls a nodepool's nodes (ADR-0037): drained and
 * rebooted in place, one at a time or `inPlace.maxUnavailable` at a time
 * (the chart's default `upgradeType` is `InPlace`), or replaced.
 */
export function rollText(r: Rebooting): string {
  const nodes = r.replicas === null ? "Its nodes" : `Its ${r.replicas} node${r.replicas === 1 ? "" : "s"}`;
  const are = r.replicas === 1 ? "is" : "are";
  if (r.replaces_nodes) {
    return `${nodes} ${are} replaced with new nodes (upgradeType: Replace): new nodes come up with the new configs, then the old ones are removed.`;
  }
  if (r.max_unavailable === null || r.max_unavailable === "") {
    return `${nodes} ${are} drained and rebooted in place, one node at a time.`;
  }
  return `${nodes} ${are} drained and rebooted in place, ${atATime(r.max_unavailable)} at a time (inPlace.maxUnavailable).`;
}

function PreviewSkeleton() {
  return (
    <div className="space-y-3" role="status" aria-label="Reading the preview">
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-40 w-full rounded-md" />
      <Skeleton className="h-16 w-full rounded-lg" />
    </div>
  );
}

/**
 * "Sync to flavor" (ADR-0037): one day1 MR sets every locked value the
 * cluster file does not hold and moves its header to the flavor's version.
 * The preview is read first, and again for each hardware choice; every
 * config the sync removes is confirmed on its own; how merging rolls each
 * nodepool's nodes is stated. Missing add-ons are not in that MR: once it is
 * open they are offered through day2, as the drift tab's Fix all does.
 *
 * Mount it while open: its state is one sync's.
 */
export function SyncDialog({
  name,
  where,
  onClose,
  onInstallAddons,
}: {
  name: string;
  /** `?site=&mce=`, as the page's other cluster calls send it. */
  where: string;
  onClose: () => void;
  /** Install missing add-ons through day2 (the drift tab's Fix all). */
  onInstallAddons: (entries: AddonDrift[]) => Promise<unknown>;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const path = `/api/day1/clusters/${encodeURIComponent(name)}`;
  const { data: catalog, isLoading: catalogLoading, error: catalogError } = useMachineConfigs();

  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [confirmed, setConfirmed] = useState<Set<string>>(() => new Set());
  /** A sync was refused as stale (409): the preview was read again. */
  const [stale, setStale] = useState(false);
  /** The MR is open; what is left is day2's. */
  const [opened, setOpened] = useState<{ mr: MRDetail; preview: SyncPreview } | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<unknown>(null);

  const hardware = useMemo<HardwareChoice[]>(
    () =>
      Object.values(choices)
        .map((c) => ({ nodepool: c.nodepool.index, hardware: c.hardware }))
        .sort((a, b) => a.nodepool - b.nodepool),
    [choices]
  );

  const preview = useQuery<SyncPreview>({
    queryKey: ["clusters", name, "sync-preview", where, hardware],
    queryFn: () => api.post<SyncPreview>(`${path}/sync/preview${where}`, { hardware } satisfies SyncPreviewRequest),
    placeholderData: keepPreviousData,
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const data = preview.data;
  // The preview on screen is not the one for the current choices yet, or is being read again
  const reading = preview.isFetching || preview.isPlaceholderData;

  const sync = useMutation({
    mutationFn: (p: SyncPreview) =>
      api.post<MRDetail>(`${path}/sync${where}`, {
        last_commit_id: p.last_commit_id,
        spec_version: p.spec_version,
        hardware,
        confirm_removals: p.removals.map((r) => ({ nodepool: r.nodepool.index, name: r.name })),
      } satisfies SyncRequest),
    onSuccess: (mr, p) => {
      toastMrOpened(mr, router.push, "Sync MR");
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      if (p.addons_to_install.length > 0 || p.addons_error) setOpened({ mr, preview: p });
      else onClose();
    },
    onError: (e) => {
      if (isApiError(e, "REVISION_CONFLICT")) {
        // The file or the flavor moved since the preview: read it again, and confirm again
        setStale(true);
        setConfirmed(new Set());
        void preview.refetch();
      }
    },
  });

  // Nodepools whose hardware is chosen here: those the preview asks about, and those already chosen
  const deciding = useMemo(() => {
    const byIndex = new Map<number, { nodepool: NodepoolRef; reason: string | null }>();
    for (const change of data?.changes ?? []) {
      if (change.needs_hardware && change.nodepool && !byIndex.has(change.nodepool.index)) {
        byIndex.set(change.nodepool.index, { nodepool: change.nodepool, reason: change.needs_decision });
      }
    }
    for (const c of Object.values(choices)) byIndex.set(c.nodepool.index, { nodepool: c.nodepool, reason: c.reason });
    return [...byIndex.values()].sort((a, b) => a.nodepool.index - b.nodepool.index);
  }, [data, choices]);

  const hardwareOptions = useMemo<ComboboxOption[]>(() => hardwareOptionsOf(catalog), [catalog]);

  // A nodepool the preview asks about starts at the generic network config, when mc-files/ has it: it
  // serves any hardware. Once per nodepool, so a person who clears or changes it is not overruled.
  const startHardware = defaultHardware(catalog);
  const defaulted = useRef<Set<number>>(new Set());
  useEffect(() => {
    if (!startHardware || !data) return;
    const fresh = data.changes.filter(
      (c) => c.needs_hardware && c.nodepool && !defaulted.current.has(c.nodepool.index) && !choices[c.nodepool.index]
    );
    if (fresh.length === 0) return;
    for (const c of fresh) defaulted.current.add(c.nodepool!.index);
    setChoices((prev) => {
      const next = { ...prev };
      for (const c of fresh) next[c.nodepool!.index] = { nodepool: c.nodepool!, reason: c.needs_decision, hardware: startHardware };
      return next;
    });
  }, [data, choices, startHardware]);

  const choose = (nodepool: NodepoolRef, reason: string | null, value: string | null) => {
    sync.reset();
    setChoices((prev) => {
      const next = { ...prev };
      if (value) next[nodepool.index] = { nodepool, reason, hardware: value };
      else delete next[nodepool.index];
      return next;
    });
  };

  const toggle = (r: ConfigRemoval, on: boolean) =>
    setConfirmed((prev) => {
      const next = new Set(prev);
      if (on) next.add(removalKey(r));
      else next.delete(removalKey(r));
      return next;
    });

  const removals = data?.removals ?? [];
  const confirmedCount = removals.filter((r) => confirmed.has(removalKey(r))).length;
  const allConfirmed = confirmedCount === removals.length;
  const canSubmit = Boolean(data) && !reading && !preview.isError && data!.can_sync && allConfirmed && !sync.isPending;

  const blockedBecause = !data || reading
    ? null
    : preview.isError
    ? null
    : data.problems.length > 0
    ? "Resolve the problems above to sync."
    : !data.can_sync
    ? "Nothing to sync: the file holds every locked value and names the flavor's current version."
    : !allConfirmed
    ? `Confirm each removal to sync (${confirmedCount} of ${removals.length} confirmed).`
    : null;

  const headerMoves = data && data.file_spec_version !== data.spec_version;
  const title = data ? `Sync ${data.cluster} to ${data.spec_name} v${data.spec_version}` : `Sync ${name} to its flavor`;

  const install = async (entries: AddonDrift[]) => {
    setInstalling(true);
    setInstallError(null);
    try {
      await onInstallAddons(entries);
      onClose();
    } catch (e) {
      setInstallError(e);
    } finally {
      setInstalling(false);
    }
  };

  // ── After the MR: the add-ons are day2's ──
  if (opened) {
    const { mr, preview: done } = opened;
    const entries = done.addons_to_install;
    return (
      <Dialog open onOpenChange={(open) => { if (!open && !installing) onClose(); }}>
        <DialogContent className="sm:max-w-2xl" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Sync MR !{mr.iid} opened</DialogTitle>
            <DialogDescription>
              It changes only the cluster file, and nothing changes on the cluster until it is merged.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3" data-testid="sync-addons-offer">
            {entries.length > 0 && (
              <Section title="Add-ons still missing" icon={Package} testId="sync-addons-missing">
                <p className="text-sm">
                  {done.spec_name} lists {entries.length} add-on{entries.length !== 1 ? "s" : ""} this cluster does not
                  have. Day1 never writes day2, so {entries.length !== 1 ? "they are" : "it is"} installed there: one MR
                  each, at the team&apos;s default version, with the values requested at create.
                </p>
                <ul className="divide-y text-sm">
                  {entries.map((e) => (
                    <li key={`${e.team}/${e.addon_name}`} className="flex items-center gap-2 py-1.5">
                      <span className="font-mono font-medium">{e.addon_name}</span>
                      <span className="text-xs text-muted-foreground">{e.team}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {done.addons_error && (
              <p className="flex items-start gap-1.5 text-sm text-status-warning-fg">
                <TriangleAlert className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
                <span className="break-words">
                  Day2 did not answer, so whether add-ons are missing is unknown ({done.addons_error}). Check the
                  Drift tab once it answers.
                </span>
              </p>
            )}
            {Boolean(installError) && (
              <ProblemList error={installError} title={writeErrorTitle(installError, "An install failed")} />
            )}
          </div>
          <DialogFooter>
            <button onClick={onClose} disabled={installing} className={buttonVariants({ variant: "outline" })}>
              {entries.length > 0 ? "Not now" : "Close"}
            </button>
            {entries.length > 0 && (
              <button onClick={() => install(entries)} disabled={installing} className={buttonVariants()}>
                {installing && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                {installing ? "Opening install MRs…" : `Install ${entries.length} add-on${entries.length !== 1 ? "s" : ""}`}
              </button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !sync.isPending) onClose(); }}>
      <DialogContent className="sm:max-w-3xl" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="break-words leading-snug">{title}</DialogTitle>
          <DialogDescription>
            One day1 merge request sets every value the flavor locks that the cluster file does not hold
            {headerMoves && data?.file_spec_version && <>, and moves its header from v{data.file_spec_version} to v{data.spec_version}</>}
            . Nothing else in the file changes: not vlanId, dhcp_values, mcFiles, mcConfigMap, the CI block or comments.
          </DialogDescription>
        </DialogHeader>

        {sync.isPending ? (
          <MRCreationProgress />
        ) : (
          <div className="max-h-[60vh] overflow-y-auto space-y-3 py-1 -mx-1 px-1">
            {stale && (
              <div role="status" data-testid="sync-stale" className="flex items-start gap-2 rounded-lg border border-status-warning/30 bg-status-warning/5 p-3 text-sm text-status-warning-fg">
                <RotateCcw className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
                <p>
                  The cluster file or the flavor changed since the preview, so no MR was opened. The preview below
                  was read again: check it, and confirm its removals again.
                </p>
              </div>
            )}

            {Boolean(sync.error) && !isApiError(sync.error, "REVISION_CONFLICT") && (
              <ProblemList error={sync.error} title={writeErrorTitle(sync.error, "The sync was refused")} />
            )}

            {deciding.length > 0 && (
              <Section title="Network hardware" icon={Network} testId="sync-hardware">
                <p className="text-xs text-muted-foreground">
                  {startHardware ? (
                    <>
                      Each nodepool below starts at the generic network config (nm-conf, for any hardware). Choose a
                      hardware type instead if a nodepool needs its own; the preview is read again with your choice.
                    </>
                  ) : (
                    <>
                      Wingman never guesses a nodepool&apos;s network hardware: a wrong network config breaks its nodes&apos;
                      networking. Choose it for each nodepool below; the preview is read again with your choice.
                    </>
                  )}
                </p>
                {catalogError ? (
                  <ProblemList error={catalogError} title="The hardware types could not be read" />
                ) : (
                  <ul className="space-y-2.5">
                    {deciding.map(({ nodepool, reason }) => (
                      <li key={nodepool.index} className="grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_12rem] sm:items-start">
                        <div className="min-w-0 text-sm">
                          <p className="font-medium break-all">{nodepool.name}</p>
                          <p className="text-xs text-muted-foreground break-words">{reason ?? `nodepool[${nodepool.index}]`}</p>
                        </div>
                        <Combobox
                          options={hardwareOptions}
                          value={choices[nodepool.index]?.hardware ?? null}
                          onValueChange={(v) => choose(nodepool, reason, v)}
                          placeholder={catalogLoading ? "Loading…" : "Choose hardware"}
                          searchPlaceholder="Search hardware types…"
                          emptyMessage="No hardware type matches."
                          disabled={catalogLoading || sync.isPending}
                          aria-label={`Hardware type for ${nodepool.name}`}
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            )}

            {preview.isError ? (
              <div className="space-y-2">
                <ProblemList
                  error={preview.error}
                  title={isApiError(preview.error, 422) ? "The sync cannot be previewed" : "The preview could not be read"}
                />
                <button onClick={() => preview.refetch()} className={buttonVariants({ variant: "outline", size: "sm" })}>
                  <RotateCcw className="h-3.5 w-3.5 mr-1.5" />Preview again
                </button>
              </div>
            ) : !data ? (
              <PreviewSkeleton />
            ) : (
              <div className={cn("space-y-3 transition-opacity", reading && "opacity-60")} aria-busy={reading}>
                {reading && (
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />Reading the preview again…
                  </p>
                )}

                {data.problems.length > 0 && (
                  <div data-testid="sync-problems">
                    <ProblemList lines={data.problems} title="These block the sync" />
                  </div>
                )}

                {removals.length > 0 && (
                  <Section title="Configs this sync removes" icon={TriangleAlert} tone="warning" testId="sync-removals">
                    <p className="text-xs text-muted-foreground">
                      The flavor&apos;s configs are exact, so a config it does not list is removed. Confirm each one.
                    </p>
                    <ul className="space-y-1.5">
                      {removals.map((r) => (
                        <li key={removalKey(r)}>
                          <label className="flex items-start gap-2.5 text-sm cursor-pointer">
                            <input
                              type="checkbox"
                              className="mt-0.5 h-4 w-4 shrink-0 accent-primary cursor-pointer"
                              checked={confirmed.has(removalKey(r))}
                              onChange={(e) => toggle(r, e.target.checked)}
                              disabled={reading}
                            />
                            <span className="min-w-0 break-words">
                              Remove <span className="font-mono font-medium">{r.name}</span> from nodepool{" "}
                              <span className="break-all">{r.nodepool.name}</span>
                              <span className="text-muted-foreground"> (nodepool[{r.nodepool.index}])</span>
                            </span>
                          </label>
                        </li>
                      ))}
                    </ul>
                  </Section>
                )}

                {data.rebooting.length > 0 && (
                  <Section title="Merging rolls these nodes" icon={RotateCw} tone="warning" testId="sync-rolling">
                    <p className="text-xs text-muted-foreground">
                      OpenShift applies changed machine configs by rolling a nodepool&apos;s nodes.
                    </p>
                    <ul className="space-y-1.5 text-sm">
                      {data.rebooting.map((r) => (
                        <li key={r.nodepool.index} data-testid={`sync-roll-${r.nodepool.index}`}>
                          <span className="font-medium break-all">{r.nodepool.name}</span>
                          <span className="text-muted-foreground"> (nodepool[{r.nodepool.index}])</span>
                          <p>{rollText(r)}</p>
                        </li>
                      ))}
                    </ul>
                    <p className="text-sm font-medium">
                      Nothing rolls until the MR is merged: merging is what starts it. Merge it in a window the
                      cluster&apos;s owners accept.
                    </p>
                  </Section>
                )}

                {data.warnings.length > 0 && (
                  <Section title="Check before merging" icon={TriangleAlert} tone="warning" testId="sync-warnings">
                    <ul className="list-disc pl-4 space-y-0.5 text-sm">
                      {data.warnings.map((w, i) => <li key={i} className="break-words">{w}</li>)}
                    </ul>
                  </Section>
                )}

                {(data.addons_to_install.length > 0 || data.addons_error) && (
                  <Section title="Not in this MR: add-ons" icon={Package} testId="sync-addons">
                    {data.addons_to_install.length > 0 && (
                      <p className="text-sm">
                        {data.addons_to_install.length} add-on{data.addons_to_install.length !== 1 ? "s" : ""} the flavor
                        lists {data.addons_to_install.length !== 1 ? "are" : "is"} missing (
                        <span className="font-mono">{data.addons_to_install.map((a) => a.addon_name).join(", ")}</span>).
                        Day2 installs them; once the sync MR is open you can install them from here.
                      </p>
                    )}
                    {data.addons_error && (
                      <p className="text-sm text-status-warning-fg break-words">
                        Day2 did not answer, so whether add-ons are missing is unknown ({data.addons_error}).
                      </p>
                    )}
                  </Section>
                )}

                {/* The evidence last: what the MR commits, line by line */}
                <section data-testid="sync-diff" aria-label="The cluster file change" className="space-y-1.5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    The cluster file change
                  </h3>
                  <p className="font-mono text-[11px] text-muted-foreground break-all">{data.path}</p>
                  {data.diff ? (
                    <YamlDiffViewer diff={data.diff} className="max-h-72" />
                  ) : (
                    <p className="text-sm text-muted-foreground italic">No change to the file.</p>
                  )}
                </section>
              </div>
            )}
          </div>
        )}

        <DialogFooter className="sm:items-center">
          {blockedBecause && (
            <p className="text-xs text-muted-foreground sm:mr-auto" data-testid="sync-blocked">{blockedBecause}</p>
          )}
          <button onClick={onClose} disabled={sync.isPending} className={buttonVariants({ variant: "outline" })}>
            Back
          </button>
          <button
            onClick={() => {
              if (!data) return;
              setStale(false);
              sync.mutate(data);
            }}
            disabled={!canSubmit}
            className={buttonVariants()}
          >
            {sync.isPending ? "Creating MR…" : "Open sync MR"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

