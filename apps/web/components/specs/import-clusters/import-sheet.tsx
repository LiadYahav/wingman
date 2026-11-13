"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog as SheetPrimitive } from "@base-ui/react/dialog";
import { ArrowLeft, Loader2, RotateCcw } from "lucide-react";
import { isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { writeErrorTitle } from "@/lib/write-errors";
import { buttonVariants } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { ProblemList } from "@/components/common/problem-list";
import {
  MAX_IMPORT,
  NO_FILTERS,
  PickStep,
  type PickFilters,
} from "@/components/specs/import-clusters/pick-step";
import { ResultStep } from "@/components/specs/import-clusters/result-step";
import { ReviewSkeleton, ReviewStep, isImported } from "@/components/specs/import-clusters/review-step";
import { cn } from "@/lib/utils";
import type {
  ClusterPick,
  ClusterStatus,
  ImportPreviewRequest,
  ImportRequest,
} from "@/types";

type Step = "pick" | "review" | "result";

const STEPS: { id: Step; label: string }[] = [
  { id: "pick", label: "Pick clusters" },
  { id: "review", label: "Review and import" },
  { id: "result", label: "Merge requests" },
];

/**
 * A 409 REVISION_CONFLICT on import: a picked file, or the flavor, moved
 * since the preview (checked before any MR opens), or every MR's file moved
 * before its commit. Either way no MR opened.
 */
const STALE_PREVIEW =
  "A cluster file or the flavor changed since this preview, so nothing was imported. Preview again to compare the current files.";

function Steps({ step }: { step: Step }) {
  return (
    <ol className="flex items-center gap-2 text-xs" aria-label="Steps">
      {STEPS.map((s, i) => {
        const current = s.id === step;
        const done = STEPS.findIndex((x) => x.id === step) > i;
        return (
          <li key={s.id} className="flex items-center gap-2" aria-current={current ? "step" : undefined}>
            {i > 0 && <span className="h-px w-6 bg-border" aria-hidden />}
            <span
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold tabular-nums",
                current ? "bg-primary text-primary-foreground" : done ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
              )}
            >
              {i + 1}
            </span>
            <span className={cn(current ? "font-medium text-foreground" : "text-muted-foreground")}>{s.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** The flow inside the sheet; it mounts when the sheet opens, so each opening starts fresh. */
function ImportFlow({ flavor }: { flavor: string }) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("pick");
  const [filters, setFilters] = useState<PickFilters>(NO_FILTERS);
  const [picked, setPicked] = useState<Map<string, ClusterStatus>>(new Map());
  const [moved, setMoved] = useState<Set<string>>(new Set());

  const preview = useMutation({
    mutationFn: (clusters: ClusterPick[]) =>
      day1Api.specs.importPreview(flavor, { clusters } satisfies ImportPreviewRequest),
  });

  // One MR per cluster (ADR-0044): the result step lists each, and each that did not open.
  // When none opened the answer is a problem; an unconfirmed write may still have opened one.
  const importer = useMutation({
    mutationFn: (body: ImportRequest) => day1Api.specs.importClusters(flavor, body),
    onSuccess: () => setStep("result"),
    onSettled: () => queryClient.invalidateQueries({ queryKey: day1Keys.approvals.all }),
  });

  const runPreview = () => {
    importer.reset();
    setStep("review");
    // Site and MCE pin each file: the list knows where every pick is
    preview.mutate([...picked.values()].map((c) => ({ name: c.name, site: c.site, mce: c.mce })));
  };

  const result = preview.data;
  const imported = result ? result.clusters.filter((c) => isImported(c, moved)) : [];
  const leftOut = result ? result.clusters.length - imported.length : 0;
  const stale = isApiError(importer.error, "REVISION_CONFLICT");

  const runImport = () => {
    if (!result) return;
    importer.mutate({
      spec_version: result.spec_version,
      clusters: imported.map((c) => ({
        name: c.name,
        site: c.site,
        mce: c.mce,
        last_commit_id: c.last_commit_id,
        relink: c.status === "relink",
      })),
    });
  };

  return (
    <>
      <div className="space-y-3 border-b px-5 pt-5 pb-4 pr-12">
        <div className="space-y-1">
          <SheetPrimitive.Title className="font-heading text-base font-semibold">Add existing clusters</SheetPrimitive.Title>
          <SheetPrimitive.Description className="text-sm text-muted-foreground">
            Link clusters Wingman did not create to <span className="font-medium text-foreground">{flavor}</span>. One
            import takes up to {MAX_IMPORT} clusters and opens a merge request for each, changing only its file&apos;s
            header.
          </SheetPrimitive.Description>
        </div>
        <Steps step={step} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {step === "result" && importer.data ? (
          <ResultStep flavor={flavor} result={importer.data} />
        ) : step === "pick" ? (
          <PickStep
            flavor={flavor}
            filters={filters}
            onFiltersChange={setFilters}
            picked={picked}
            onPickedChange={setPicked}
          />
        ) : preview.isPending ? (
          <ReviewSkeleton count={picked.size} />
        ) : preview.error ? (
          <ProblemList error={preview.error} title="The import could not be previewed" />
        ) : result ? (
          <ReviewStep
            flavor={flavor}
            preview={result}
            moved={moved}
            onMovedChange={(key, on) =>
              setMoved((prev) => {
                const next = new Set(prev);
                if (on) next.add(key);
                else next.delete(key);
                return next;
              })
            }
          />
        ) : null}
      </div>

      {/* What the import did, next to the actions */}
      {step === "review" && importer.error && (
        <div className="border-t px-5 py-3">
          {stale ? (
            <div
              role="alert"
              data-testid="import-stale"
              className="flex items-start justify-between gap-3 rounded-lg border border-status-warning/30 bg-status-warning/5 p-3 text-sm"
            >
              <p className="text-status-warning-fg">{STALE_PREVIEW}</p>
              <button onClick={runPreview} className={buttonVariants({ variant: "outline", size: "sm" })}>
                <RotateCcw className="h-3.5 w-3.5" />Preview again
              </button>
            </div>
          ) : (
            <ProblemList error={importer.error} title={writeErrorTitle(importer.error, "The import was refused")} />
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-muted/40 px-5 py-3">
        {step === "pick" ? (
          <>
            <p className="text-xs text-muted-foreground" data-testid="import-picked-count">
              {picked.size === 0 ? "Pick the clusters to import" : `${picked.size} of at most ${MAX_IMPORT} picked`}
              {picked.size > 0 && (
                <button
                  type="button"
                  onClick={() => setPicked(new Map())}
                  className="ml-2 font-medium text-foreground/80 underline-offset-2 hover:underline"
                >
                  Clear
                </button>
              )}
            </p>
            <div className="flex items-center gap-2">
              <SheetPrimitive.Close className={buttonVariants({ variant: "outline" })}>Cancel</SheetPrimitive.Close>
              <button onClick={runPreview} disabled={picked.size === 0} className={buttonVariants()}>
                Preview {picked.size > 0 ? picked.size : ""} cluster{picked.size !== 1 ? "s" : ""}
              </button>
            </div>
          </>
        ) : step === "result" ? (
          <>
            <p className="text-xs text-muted-foreground" data-testid="import-summary">
              {importer.data && importer.data.failed.length > 0
                ? `${importer.data.merge_requests.length} opened · ${importer.data.failed.length} not opened`
                : `${importer.data?.merge_requests.length ?? 0} opened`}
            </p>
            <SheetPrimitive.Close className={buttonVariants()}>Done</SheetPrimitive.Close>
          </>
        ) : (
          <>
            <p className="text-xs text-muted-foreground" data-testid="import-summary">
              {result
                ? leftOut > 0
                  ? `${imported.length} to link · ${leftOut} left out`
                  : `${imported.length} to link`
                : " "}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { importer.reset(); setStep("pick"); }}
                disabled={importer.isPending}
                className={buttonVariants({ variant: "outline" })}
              >
                <ArrowLeft className="h-3.5 w-3.5" />Back
              </button>
              <button
                onClick={runImport}
                disabled={!result || imported.length === 0 || importer.isPending || stale}
                className={buttonVariants()}
              >
                {importer.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Opening {imported.length} merge request{imported.length !== 1 ? "s" : ""}…
                  </>
                ) : (
                  `Import ${imported.length} cluster${imported.length !== 1 ? "s" : ""}`
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

/**
 * "Add existing clusters" (ADR-0037, admins only): pick clusters Wingman did
 * not create, preview each against the flavor, and open one day1 MR per
 * cluster that links it (ADR-0044); the last step lists each MR and each
 * cluster whose MR did not open. An MR writes only the flavor link into its
 * file's header.
 */
export function ImportClustersSheet({
  flavor,
  open,
  onOpenChange,
}: {
  flavor: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 data-[side=right]:sm:max-w-3xl" data-testid="import-sheet">
        {open && <ImportFlow flavor={flavor} />}
      </SheetContent>
    </Sheet>
  );
}

