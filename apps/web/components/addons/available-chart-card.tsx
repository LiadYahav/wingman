"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Package, Plus } from "lucide-react";
import { api } from "@/lib/api-client";
import { day2Api } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { toYaml, type Values } from "@/lib/values";
import { buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ProblemList } from "@/components/common/problem-list";
import { ReviewDialog } from "@/components/common/review-dialog";
import { FindingsBadge, FindingsList } from "@/components/addons/findings";
import { ValuesEditor } from "@/components/addons/values-editor";
import { FilePreview, MessageField, WriteError, type PlannedFile } from "@/components/addons/file-preview";
import { VersionField } from "@/components/addons/version-field";
import { useValuesPreview } from "@/components/addons/use-values-preview";
import type { DestinationRef } from "@/components/addons/installed-chart-card";
import type { OpenedChanges } from "@/components/addons/change-result";
import type { CatalogEntry, ChangeResult, InstallBody, ValuesPreview } from "@/types/day2";

const EMPTY: Values = {};

/** Everything an install needs besides the chart: its values, and a pin only if asked for. */
export interface InstallChoice {
  values: Values;
  version: string | null;
  emergencyPin: boolean;
  repourl: string;
}

export const DEFAULT_CHOICE: InstallChoice = { values: EMPTY, version: null, emergencyPin: false, repourl: "" };

/**
 * No layer of the deploy config sets a lowercase `repourl` (the add-on may
 * have only the miscased `repoUrl`), so the install must give one. The
 * preview knows what this destination inherits; the catalog only the add-on's.
 */
export function needsRepourl(entry: CatalogEntry, preview?: ValuesPreview): boolean {
  return !(preview ? preview.deploy.repo_url : entry.argocd_metadata.repourl);
}

/**
 * The install form: the chart's would-be values on the destination, with the
 * cluster folder's `values.yaml` as the file being written. Shared by a single
 * install and by each chart of a bulk install.
 */
export function InstallForm({
  entry,
  destination,
  choice,
  onChange,
  excludedHere,
  preview,
}: {
  entry: CatalogEntry;
  destination: DestinationRef;
  choice: InstallChoice;
  onChange: (next: InstallChoice) => void;
  excludedHere: boolean;
  preview: InstallPreview;
}) {
  const data = preview.data;
  const inherited = data?.deploy.target_revision ?? entry.current_version;
  const valuesPath = installPaths(entry, data).values;
  return (
    <div className="space-y-4">
      <FindingsList findings={entry.warnings} showContext />
      {excludedHere && (
        <p className="rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          {entry.name} is a fleet default of {entry.team} that <code>exclusions.yaml</code> keeps off {destination.name};
          installing it gives {destination.name} its own copy in its folder.
        </p>
      )}
      {needsRepourl(entry, data) && (
        <label className="block space-y-1 text-xs">
          <span className="font-semibold uppercase tracking-wide text-muted-foreground">Chart repo URL (repourl)</span>
          <input
            type="url"
            required
            value={choice.repourl}
            onChange={(e) => onChange({ ...choice, repourl: e.target.value })}
            placeholder="https://gitlab.example.com/helm-charts/chart.git"
            className="h-8 w-full rounded-lg border bg-background px-3 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          <span className="block text-muted-foreground">
            No layer of the deploy config has a lowercase <code>repourl</code>, so this cluster&apos;s folder must set it.
          </span>
        </label>
      )}
      {entry.available_versions.length > 0 && (
        <VersionField
          versions={entry.available_versions}
          inherited={inherited}
          pinned={false}
          value={choice.version ?? inherited}
          onChange={(v) => onChange({ ...choice, version: v === inherited ? null : v, emergencyPin: false })}
          emergencyPin={choice.emergencyPin}
          onEmergencyPinChange={(pin) => onChange({ ...choice, emergencyPin: pin })}
          clusterName={destination.name}
        />
      )}
      {preview.error && !data ? (
        <ProblemList error={preview.error} title="The values could not be loaded" />
      ) : (
        <ValuesEditor
          preview={data}
          loading={preview.isLoading}
          stale={preview.stale}
          file={{ role: "cluster", path: valuesPath }}
          draft={choice.values}
          baseline={EMPTY}
          onDraftChange={(values) => onChange({ ...choice, values })}
        />
      )}
    </div>
  );
}

/** The preview of `entry` on the destination with the install's values as its folder's `values.yaml`. */
export function useInstallPreview(entry: CatalogEntry, destination: DestinationRef, choice: InstallChoice, enabled: boolean) {
  return useValuesPreview({
    clusterId: destination.id,
    team: entry.team,
    chart: entry.name,
    version: choice.version ?? undefined,
    draft: choice.values,
    baseline: EMPTY,
    enabled,
  });
}

export type InstallPreview = ReturnType<typeof useInstallPreview>;

/** Where the install writes, as the service lays the folder out (ADR-0020). */
function installPaths(entry: CatalogEntry, preview: ValuesPreview | undefined) {
  return {
    values: preview?.layers.find((l) => l.role === "cluster")?.path ?? `${entry.name}/values.yaml`,
    deploy: preview?.deploy.layers.find((l) => l.role === "cluster")?.path ?? `${entry.name}/${entry.name}.yaml`,
  };
}

/** What is still missing before the chart can be installed, or `null`. */
export function installBlocker(entry: CatalogEntry, choice: InstallChoice, preview?: ValuesPreview): string | null {
  if (needsRepourl(entry, preview) && !choice.repourl.trim()) return "Give the chart repo URL";
  if (choice.version !== null && !choice.emergencyPin) return "Confirm the emergency pin";
  return null;
}

export function installBody(choice: InstallChoice): Omit<InstallBody, "message"> {
  return {
    override_values: choice.values,
    ...(choice.version !== null ? { version: choice.version, emergency_pin: choice.emergencyPin } : {}),
    ...(choice.repourl.trim() ? { repourl: choice.repourl.trim() } : {}),
  };
}

/** A catalog chart not on the destination yet. */
export function AvailableChartCard({
  entry,
  destination,
  isAdmin,
  excludedHere,
  selected,
  onSelectChange,
  selecting,
  onOpened,
  readOnlyReason = null,
}: {
  entry: CatalogEntry;
  destination: DestinationRef;
  isAdmin: boolean;
  /** The team is read-only in Wingman (ADR-0043): Install is off, and the page says why. */
  readOnlyReason?: string | null;
  excludedHere: boolean;
  selected: boolean;
  onSelectChange: (selected: boolean) => void;
  /** Some chart is selected for a bulk install: show every checkbox. */
  selecting: boolean;
  onOpened: (changes: OpenedChanges) => void;
}) {
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<InstallChoice>(DEFAULT_CHOICE);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [writeError, setWriteError] = useState<unknown>(null);
  const preview = useInstallPreview(entry, destination, choice, open);
  const blocker = installBlocker(entry, choice, preview.data);

  const install = useMutation({
    mutationFn: () =>
      api.post<ChangeResult>(day2Api.chart(destination.id, entry.team, entry.name), {
        ...installBody(choice),
        ...(message.trim() ? { message: message.trim() } : {}),
      } satisfies InstallBody),
    onMutate: () => setWriteError(null),
    onSuccess: (mr) => {
      onOpened({ verb: "Install", results: [mr], failed: [] });
      setReviewOpen(false);
      setOpen(false);
      setChoice(DEFAULT_CHOICE);
      setMessage("");
    },
    onError: (error) => setWriteError(error),
  });

  return (
    <>
      <div
        className={cn(
          "group/card overflow-hidden rounded-xl border bg-card shadow-sm transition-[box-shadow,border-color] duration-150",
          selected && "border-primary/50 ring-2 ring-primary",
        )}
        data-testid={`available-${entry.team}-${entry.name}`}
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
          {isAdmin && !readOnlyReason && (
            <div
              className={cn(
                "transition-opacity duration-150",
                selecting || selected ? "opacity-100" : "opacity-0 focus-within:opacity-100 group-hover/card:opacity-100",
              )}
            >
              <Checkbox checked={selected} onCheckedChange={onSelectChange} />
            </div>
          )}
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/8 text-primary dark:bg-primary/15">
            <Package className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1 basis-32">
            <span className="block truncate text-sm font-semibold" title={entry.name}>
              {entry.name}
            </span>
            <span className="block truncate text-xs text-muted-foreground">
              {entry.team}
              {excludedHere ? " · excluded fleet default" : ""}
            </span>
          </span>
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            <span className="max-w-36 truncate rounded-full bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground" title={`Inherited revision ${entry.current_version}`}>
              {entry.current_version}
            </span>
            <FindingsBadge findings={entry.warnings} />
            {isAdmin &&
              (open ? (
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="px-2 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  Cancel
                </button>
              ) : (
                !selecting && (
                  <button
                    type="button"
                    onClick={() => setOpen(true)}
                    disabled={Boolean(readOnlyReason)}
                    title={readOnlyReason ?? undefined}
                    className={cn(buttonVariants({ size: "sm" }), "h-7 gap-1.5 active:scale-[0.97]")}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Install
                  </button>
                )
              ))}
          </div>
        </div>

        {open && (
          <div className="space-y-4 border-t bg-muted/10 p-4">
            <InstallForm
              entry={entry}
              destination={destination}
              choice={choice}
              onChange={setChoice}
              excludedHere={excludedHere}
              preview={preview}
            />
            <button
              type="button"
              onClick={() => setReviewOpen(true)}
              disabled={Boolean(blocker)}
              title={blocker ?? undefined}
              className="inline-flex h-7 items-center rounded-lg bg-primary px-3 text-xs font-semibold text-primary-foreground transition-[background-color,transform] duration-150 hover:bg-primary/90 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Review install
            </button>
          </div>
        )}
      </div>

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={(next) => {
          setReviewOpen(next);
          setWriteError(null);
        }}
        title={`Install ${entry.name} on ${destination.name}`}
        description={`Opens a merge request on ${entry.team}'s repo. Nothing deploys until it is merged, and a manual-sync app until someone syncs it.`}
        onConfirm={() => install.mutate()}
        isPending={install.isPending}
        size="lg"
      >
        <div className="space-y-3">
          {plannedInstall(entry, choice, preview.data).map((file) => (
            <FilePreview key={file.path} file={file} />
          ))}
          <MessageField value={message} onChange={setMessage} />
          <WriteError error={writeError} />
        </div>
      </ReviewDialog>
    </>
  );
}

/**
 * The files an install creates: the folder's `values.yaml` always, its
 * `<chart>.yaml` only for a key the inherited deploy config lacks (ADR-0022).
 */
export function plannedInstall(entry: CatalogEntry, choice: InstallChoice, preview: ValuesPreview | undefined): PlannedFile[] {
  const paths = installPaths(entry, preview);
  const files: PlannedFile[] = [{ action: "create", path: paths.values, after: toYaml(choice.values) }];
  const deploy: Values = {
    ...(choice.repourl.trim() ? { repourl: choice.repourl.trim() } : {}),
    ...(choice.version !== null && choice.emergencyPin ? { targetRevision: choice.version } : {}),
  };
  if (Object.keys(deploy).length > 0) files.push({ action: "create", path: paths.deploy, after: toYaml(deploy) });
  return files;
}
