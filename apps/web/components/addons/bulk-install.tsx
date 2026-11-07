"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Package, Plus, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { bulkProblemsOf, day2Api, problemOf, writeErrorMessage, type BulkProblem } from "@/lib/day2";
import { cn } from "@/lib/utils";
import { leaves } from "@/lib/values";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ReviewDialog } from "@/components/common/review-dialog";
import { MessageField, WriteError } from "@/components/addons/file-preview";
import {
  DEFAULT_CHOICE,
  InstallForm,
  installBlocker,
  needsRepourl,
  useInstallPreview,
  type InstallChoice,
} from "@/components/addons/available-chart-card";
import type { DestinationRef } from "@/components/addons/installed-chart-card";
import type { OpenedChanges } from "@/components/addons/change-result";
import type { BulkBody, BulkResult, CatalogEntry } from "@/types/day2";

export const chartKey = (entry: { team: string; name: string }) => `${entry.team}/${entry.name}`;

/** The floating bar that appears once a chart is selected. */
export function BulkInstallBar({ count, onClear, onInstall }: { count: number; onClear: () => void; onInstall: () => void }) {
  if (count === 0) return null;
  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-in fade-in slide-in-from-bottom-2 duration-200">
      <div className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-[var(--shadow-float)]">
        <span className="flex items-center gap-2 text-sm font-medium">
          <span className="flex h-7 min-w-7 items-center justify-center rounded-lg bg-primary px-1.5 text-sm font-bold tabular-nums text-primary-foreground">
            {count}
          </span>
          chart{count === 1 ? "" : "s"} selected
        </span>
        <span className="h-5 w-px bg-border" />
        <button type="button" onClick={onClear} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
          <X className="h-4 w-4" />
          Clear
        </button>
        <button type="button" onClick={onInstall} className={cn(buttonVariants({ size: "sm" }), "gap-1.5 active:scale-[0.97]")}>
          <Plus className="h-3.5 w-3.5" />
          Install selected
        </button>
      </div>
    </div>
  );
}

/**
 * Install several charts at once: one MR per team, every chart checked
 * before any MR opens (one refused chart refuses them all, ADR-0022).
 */
export function BulkInstallDialog({
  open,
  onOpenChange,
  entries,
  choices,
  onChoiceChange,
  destination,
  onOpened,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entries: CatalogEntry[];
  choices: Record<string, InstallChoice>;
  onChoiceChange: (key: string, choice: InstallChoice) => void;
  destination: DestinationRef;
  /** Called with the opened MRs; the caller clears the selection. */
  onOpened: (changes: OpenedChanges) => void;
}) {
  const [configuring, setConfiguring] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [problems, setProblems] = useState<BulkProblem[]>([]);

  const teams = [...new Set(entries.map((e) => e.team))].sort();
  const choiceOf = (entry: CatalogEntry) => choices[chartKey(entry)] ?? DEFAULT_CHOICE;
  const blockers = entries
    .map((entry) => {
      // A bulk item carries no repourl: such a chart goes through its own install.
      const reason = needsRepourl(entry) ? "needs a repourl: install it on its own" : installBlocker(entry, choiceOf(entry));
      return reason ? { key: chartKey(entry), reason } : null;
    })
    .filter((b): b is { key: string; reason: string } => b !== null);

  const install = useMutation({
    mutationFn: () => {
      const body: BulkBody = {
        addons: entries.map((entry) => {
          const choice = choiceOf(entry);
          return {
            team: entry.team,
            addon: entry.name,
            override_values: choice.values,
            ...(choice.version !== null ? { version: choice.version, emergency_pin: choice.emergencyPin } : {}),
          };
        }),
        ...(message.trim() ? { custom_message: message.trim() } : {}),
      };
      return api.post<BulkResult>(day2Api.bulk(destination.id), body);
    },
    onMutate: () => {
      setError("");
      setProblems([]);
    },
    onSuccess: (result) => {
      onOpened({ verb: "Install", results: result.merge_requests, failed: result.failed });
      setMessage("");
      onOpenChange(false);
    },
    onError: (e) => {
      const problem = problemOf(e);
      setError(writeErrorMessage(problem));
      setProblems(bulkProblemsOf(problem));
    },
  });

  const configured = entries.find((e) => chartKey(e) === configuring);

  return (
    <>
      <ReviewDialog
        open={open && !configured}
        onOpenChange={(next) => {
          onOpenChange(next);
          if (!next) setError("");
        }}
        title={`Install ${entries.length} chart${entries.length === 1 ? "" : "s"} on ${destination.name}`}
        description={`Opens ${teams.length === 1 ? "one merge request" : `${teams.length} merge requests, one per team`}. Every chart is checked first: if one is refused, none is opened.`}
        onConfirm={() => install.mutate()}
        isPending={install.isPending}
        confirmDisabled={blockers.length > 0 || entries.length === 0}
        confirmLabel={`Open ${teams.length} MR${teams.length === 1 ? "" : "s"}`}
        size="lg"
      >
        <div className="space-y-4">
          {teams.map((team) => (
            <section key={team} className="space-y-1.5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {team} <span className="font-normal normal-case">· one MR on sigs/{team}</span>
              </h3>
              <ul className="space-y-1.5">
                {entries
                  .filter((e) => e.team === team)
                  .map((entry) => {
                    const key = chartKey(entry);
                    const choice = choiceOf(entry);
                    const count = leaves(choice.values).length;
                    const blocker = blockers.find((b) => b.key === key);
                    const refused = problems.filter((p) => p.team === entry.team && (!p.chart || p.chart === entry.name));
                    return (
                      <li
                        key={key}
                        className={cn(
                          "rounded-lg border p-3",
                          blocker || refused.length > 0 ? "border-status-warning/40 bg-status-warning/5" : "bg-card",
                        )}
                      >
                        <div className="flex items-center gap-3">
                          <Package className="h-4 w-4 shrink-0 text-primary" />
                          <span className="min-w-0 flex-1 truncate text-sm font-semibold" title={entry.name}>
                            {entry.name}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {count > 0 ? `${count} value${count === 1 ? "" : "s"} set` : "inherits every value"}
                          </span>
                          <span className="max-w-32 truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                            {choice.version ?? entry.current_version}
                          </span>
                          <button
                            type="button"
                            onClick={() => setConfiguring(key)}
                            disabled={needsRepourl(entry)}
                            className={cn(buttonVariants({ variant: "outline", size: "xs" }))}
                          >
                            Configure
                          </button>
                        </div>
                        {(blocker || refused.length > 0) && (
                          <ul className="mt-2 space-y-0.5 pl-7 text-xs text-status-warning-fg">
                            {blocker && (
                              <li className="flex gap-1.5">
                                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                                {blocker.reason}
                              </li>
                            )}
                            {refused.map((p) => (
                              <li key={p.detail} className="flex gap-1.5">
                                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                                {p.detail}
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
              </ul>
            </section>
          ))}
          <MessageField value={message} onChange={setMessage} />
          <WriteError message={error} />
        </div>
      </ReviewDialog>

      {configured && (
        <ConfigureDialog
          key={chartKey(configured)}
          entry={configured}
          destination={destination}
          initial={choiceOf(configured)}
          onSave={(choice) => onChoiceChange(chartKey(configured), choice)}
          onClose={() => setConfiguring(null)}
        />
      )}
    </>
  );
}

function ConfigureDialog({
  entry,
  destination,
  initial,
  onSave,
  onClose,
}: {
  entry: CatalogEntry;
  destination: DestinationRef;
  initial: InstallChoice;
  onSave: (choice: InstallChoice) => void;
  onClose: () => void;
}) {
  const [choice, setChoice] = useState(initial);
  const preview = useInstallPreview(entry, destination, choice, true);
  const blocker = installBlocker(entry, choice, preview.data);
  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-4xl" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Configure {entry.name}</DialogTitle>
          <DialogDescription>Only the values you set are written; the rest are inherited.</DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto py-1">
          <InstallForm
            entry={entry}
            destination={destination}
            choice={choice}
            onChange={setChoice}
            excludedHere={false}
            preview={preview}
          />
        </div>
        <DialogFooter>
          <button type="button" onClick={onClose} className={buttonVariants({ variant: "outline" })}>
            Back
          </button>
          <button
            type="button"
            disabled={Boolean(blocker)}
            title={blocker ?? undefined}
            onClick={() => {
              onSave(choice);
              onClose();
            }}
            className={buttonVariants()}
          >
            Save
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
