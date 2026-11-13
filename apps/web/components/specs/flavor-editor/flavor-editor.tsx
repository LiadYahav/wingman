"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, ArrowLeft, Eye, RotateCcw, X } from "lucide-react";
import jsYaml from "js-yaml";
import { ApiError, errorMessages, isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { Button, buttonVariants } from "@/components/ui/button";
import { ReviewDialog } from "@/components/common/review-dialog";
import { ProblemList } from "@/components/common/problem-list";
import { configProblems } from "@/components/machine-configs/config-list-editor";
import { asNewFile, computeLineDiff } from "@/lib/diff";
import { defaultConfigs, useMachineConfigs } from "@/lib/machine-configs";
import { toastMrOpened } from "@/lib/mr-toast";
import { editVersionProblem, specNameProblem, specVersionProblem } from "@/lib/specs";
import { writeErrorTitle } from "@/lib/write-errors";
import { cn } from "@/lib/utils";
import type { ClusterSpec, SpecDetail, TemplateField } from "@/types";
import { AddonsSection } from "./addons-section";
import { BasicsSection } from "./basics-section";
import { fieldId, SectionHeader } from "./controls";
import {
  CONFIGS_RULE,
  OWNERS,
  PLATFORM,
  buildDocument,
  configsMode,
  draftIssues,
  lockNotEnforced,
  nodepoolCount,
  nodepoolPath,
  nodepoolValues,
  otherPoolInputs,
  otherTopInputs,
  pathLabel,
  removeLock,
  routeProblems,
  setLocked,
  setTopValue,
  storedForm,
  strayLocks,
  valueLines,
  type FlavorDraft,
} from "./model";
import { NodepoolsSection } from "./nodepools-section";
import { ReviewSection } from "./review-section";

const SECTIONS = [
  { id: "basics", title: "Basics", description: "What the flavor is, and the owner and platform of its clusters." },
  { id: "nodepools", title: "Nodepools", description: "The nodepools a cluster starts with, and their machine configs." },
  { id: "addons", title: "Add-ons", description: "The day2 charts every cluster of the flavor gets, in install order." },
  { id: "review", title: "Review", description: "What every cluster gets, the flavor file, and the cluster file it gives." },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];
const SECTION_IDS = SECTIONS.map((s) => s.id);

const dump = (spec: ClusterSpec) => jsYaml.dump(storedForm(spec), { lineWidth: 120, quotingType: '"', noRefs: true });

const sectionOf = (path: string): SectionId => (path.startsWith("nodepools") ? "nodepools" : "basics");

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Scroll a field (or section) into view and put the cursor in its first control. */
function reveal(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  el.querySelector<HTMLElement>("input, textarea, [role='combobox'], button[aria-checked='true'], button")?.focus({ preventScroll: true });
}

/** The section being read: the last one whose top has passed the upper part of the view. */
function useActiveSection(): SectionId {
  const [active, setActive] = useState<SectionId>("basics");
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const line = window.innerHeight * 0.35;
      let current: SectionId = "basics";
      for (const id of SECTION_IDS) {
        const top = document.getElementById(id)?.getBoundingClientRect().top;
        if (top !== undefined && top <= line) current = id;
      }
      setActive(current);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    // The page scrolls inside the app shell's <main>: listen in the capture phase to hear it.
    window.addEventListener("scroll", onScroll, { capture: true, passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("scroll", onScroll, { capture: true });
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);
  return active;
}

/**
 * The flavor editor (`docs/ideas/flavors-v2.md`, "The flavor page"): one
 * page in four parts, basics, nodepools, add-ons and review. Every value is
 * a preset or locked; machine configs come from the catalogue, prefilled
 * from the nodepool defaults; the review shows the flavor file a save
 * proposes and, for a saved flavor, the cluster file day1 renders from it.
 * A save opens an MR; day1's problems are shown at their fields.
 */
// eslint-disable-next-line max-lines-per-function, complexity -- size baseline (ADR-0056)
export function FlavorEditor({
  spec: given,
  initial: start,
  onReload,
}: {
  /** The flavor being edited, as read; absent for a new one. */
  spec?: SpecDetail;
  initial: FlavorDraft;
  /** Read the flavor again and start over from it (after a 409). */
  onReload?: () => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  // The read this edit started from: its document is the base and its commit
  // the write's guard, whatever a later read of the flavor says.
  const [spec] = useState(given);
  const [initial] = useState(start);
  const isNew = !spec;
  const [draft, setDraft] = useState<FlavorDraft>(initial);
  const update = useCallback((change: (d: FlavorDraft) => FlavorDraft) => setDraft(change), []);
  const [attempted, setAttempted] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const active = useActiveSection();

  const { data: catalog, isLoading: catalogLoading, error: catalogError } = useMachineConfigs();
  const defaults = useMemo(() => defaultConfigs(catalog), [catalog]);
  const { data: schema, error: schemaError } = useQuery<TemplateField[]>({
    queryKey: day1Keys.specs.templateSchema,
    queryFn: day1Api.specs.templateSchema,
    staleTime: 300_000,
  });
  const { data: sharedTemplate = "" } = useQuery<string>({
    queryKey: day1Keys.specs.sharedTemplate,
    queryFn: day1Api.specs.sharedTemplate,
    staleTime: 300_000,
    enabled: isNew,
  });
  const template = spec?.spec.day1.template ?? sharedTemplate;

  const document = useMemo(() => buildDocument(draft, spec ?? null), [draft, spec]);
  const yaml = useMemo(() => dump(document), [document]);
  const savedYaml = useMemo(() => (spec ? dump(buildDocument(initial, spec)) : ""), [initial, spec]);
  const diff = useMemo(() => (spec ? computeLineDiff(savedYaml, yaml) : asNewFile(yaml)), [spec, savedYaml, yaml]);
  const lines = useMemo(() => valueLines(draft), [draft]);
  const otherTop = useMemo(() => otherTopInputs(schema ?? [], draft.values), [schema, draft.values]);

  const issues = useMemo(
    () =>
      draftIssues(draft, catalog, {
        name: isNew ? specNameProblem : undefined,
        // An edit needs a new version: each cluster is measured against the one it is on (ADR-0044)
        version: spec ? (v) => editVersionProblem(v, spec.metadata.version) : specVersionProblem,
      }),
    [draft, catalog, isNew, spec]
  );

  const save = useMutation({
    // An update is guarded by the commit the flavor was read at; a stale one is a 409 (ADR-0006)
    mutationFn: () => (isNew ? day1Api.specs.create(document) : day1Api.specs.update(spec.metadata.name, spec.last_commit_id, document)),
    onSuccess: (mr) => {
      setReviewOpen(false);
      queryClient.invalidateQueries({ queryKey: day1Keys.specs.all });
      if (isNew) {
        toastMrOpened(mr, router.push, "Flavor MR");
        router.push("/specs");
      } else {
        toastMrOpened(mr, router.push, "Update MR");
        router.push(`/specs/${encodeURIComponent(spec.metadata.name)}`);
      }
    },
    onError: () => {
      setReviewOpen(false);
      requestAnimationFrame(() => reveal("flavor-problems"));
    },
  });

  // Day1's 422 problems, each at its field (§1: every problem starts with its path)
  const fields = useMemo(() => {
    const list = ["metadata.version", "metadata.description", ...OWNERS.map((o) => o.path), PLATFORM, ...otherTop.map((i) => i.name)];
    if (isNew) list.push("metadata.name");
    if (configsMode(draft) === "rule") list.push(CONFIGS_RULE);
    for (let i = 0; i < nodepoolCount(draft); i++) {
      list.push(nodepoolPath(i, "replicas"), nodepoolPath(i, "configs"), nodepoolPath(i, "node_labels"));
      for (const input of otherPoolInputs(schema ?? [], nodepoolValues(draft, i))) list.push(nodepoolPath(i, input.name));
    }
    return list;
  }, [draft, schema, otherTop, isNew]);
  const refused = isApiError(save.error, "VALIDATION_ERROR") ? save.error : null;
  const server = useMemo(
    () => (refused ? routeProblems(refused.messages(), fields) : { routed: [], unmatched: [] }),
    [refused, fields]
  );
  const rawServer = useMemo(() => (refused ? refused.problems : []), [refused]);

  const problemsAt = useCallback(
    (path: string, { deeper = false }: { deeper?: boolean } = {}) => [
      ...issues.filter((i) => i.path === path && i.entry === undefined).map((i) => i.message),
      ...server.routed
        .filter((r) => r.field === path && (deeper || r.path === path))
        .map((r) => {
          if (r.path === path) return r.message;
          const rel = r.path.slice(path.length);
          const entry = /^\[(\d+)\]$/.exec(rel);
          return entry && path.endsWith(".configs") ? `Config ${Number(entry[1]) + 1}: ${r.message}` : `${rel}: ${r.message}`;
        }),
    ],
    [issues, server]
  );
  const configProblemsAt = useCallback((path: string) => configProblems(rawServer, path), [rawServer]);
  // A saved lock that breaks a rule is not enforced at create (`enforced_locks`); its field says so
  const notEnforced = useCallback((path: string) => lockNotEnforced(spec, path), [spec]);

  const counts = useMemo(() => {
    const out: Record<SectionId, number> = { basics: 0, nodepools: 0, addons: 0, review: 0 };
    for (const issue of issues) {
      if (issue.path.startsWith("metadata.") && !attempted && !(issue.path === "metadata.name" ? draft.name : draft.version)) continue;
      out[sectionOf(issue.path)]++;
    }
    for (const r of server.routed) out[sectionOf(r.field)]++;
    return out;
  }, [issues, server, attempted, draft.name, draft.version]);

  const handleReview = () => {
    setAttempted(true);
    if (issues.length > 0) {
      reveal(fieldId(issues[0].path));
      return;
    }
    save.reset();
    setReviewOpen(true);
  };

  const stray = strayLocks(draft);
  const warnings = spec?.warnings ?? [];
  const backHref = spec ? `/specs/${encodeURIComponent(spec.metadata.name)}` : "/specs";
  const title = isNew ? "New Flavor" : "Edit Flavor";

  return (
    <div className="mx-auto max-w-5xl px-4 pb-24 sm:px-6 lg:px-8">
      <div className="flex items-center gap-3 pb-5 pt-6">
        <Link href={backHref} className={buttonVariants({ variant: "ghost", size: "icon" })} aria-label={isNew ? "Back to flavors" : "Back to the flavor"}>
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold leading-tight tracking-[-0.02em]">{title}</h1>
          <p className="mt-0.5 truncate text-sm text-muted-foreground">
            {isNew ? (
              "A flavor presets or locks what a cluster is created with."
            ) : (
              <>
                Editing <span className="font-medium text-foreground">{spec.metadata.name}</span> · saved as v{spec.metadata.version}
              </>
            )}
          </p>
        </div>
      </div>

      <nav
        aria-label="Flavor parts"
        className="sticky top-0 z-20 -mx-4 border-b border-border/70 bg-background/80 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-background/65 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8"
      >
        <div className="flex items-center gap-3 py-2.5">
          <ol className="-mx-1 flex min-w-0 items-center gap-0.5 overflow-x-auto px-1">
            {SECTIONS.map((section, index) => {
              const current = active === section.id;
              const count = counts[section.id];
              return (
                <li key={section.id}>
                  <button
                    type="button"
                    onClick={() => reveal(section.id)}
                    aria-current={current ? "step" : undefined}
                    className={cn(
                      "flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm whitespace-nowrap outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring/60",
                      current ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <span className="hidden text-xs tabular text-muted-foreground sm:inline">{index + 1}</span>
                    {section.title}
                    {count > 0 && (
                      <span
                        className="ml-0.5 rounded-full bg-destructive/15 px-1.5 text-[10px] font-semibold leading-4 text-destructive tabular"
                        aria-label={`${count} to fix`}
                      >
                        {count}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Link href={backHref} className={cn(buttonVariants({ variant: "ghost" }), "hidden sm:inline-flex")}>
              Cancel
            </Link>
            <Button onClick={handleReview} disabled={save.isPending}>
              <Eye /> {isNew ? "Review & Create" : "Review & Update"}
            </Button>
          </div>
        </div>
      </nav>

      <div className="space-y-12 pt-6">
        {(warnings.length > 0 || stray.length > 0 || save.error || (attempted && issues.length > 0) || catalogError || schemaError) && (
          <div id="flavor-problems" className="scroll-mt-28 space-y-3">
            {(warnings.length > 0 || stray.length > 0) && (
              <div role="status" data-testid="flavor-warnings" className="rounded-xl border border-status-warning/30 bg-status-warning/10 px-4 py-3 text-sm text-status-warning-fg">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  <div className="min-w-0 space-y-2">
                    {warnings.length > 0 && (
                      <div>
                        <p className="font-medium">This flavor breaks rules a save checks. It still works, but saving it unchanged would be refused:</p>
                        <ul className="mt-1 list-disc space-y-0.5 pl-4">
                          {warnings.map((w) => (
                            <li key={w} className="break-words">{w}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {stray.length > 0 && (
                      <div>
                        <p className="font-medium">Locks this page cannot show (not lockable, or on a nodepool the flavor does not have):</p>
                        <ul className="mt-1 flex flex-wrap gap-1.5">
                          {stray.map((path) => (
                            <li key={path} className="inline-flex items-center gap-1 rounded-md border border-status-warning/30 bg-background/60 py-0.5 pl-2 pr-0.5 font-mono text-xs">
                              {path}
                              <button
                                type="button"
                                className="rounded p-0.5 hover:bg-status-warning/20"
                                aria-label={`Remove the lock on ${path}`}
                                onClick={() => update((d) => removeLock(d, path))}
                              >
                                <X className="h-3 w-3" />
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {save.error && <SaveProblems error={save.error} unmatched={server.unmatched} routed={server.routed.length} name={document.metadata.name} onReload={onReload} />}

            {attempted && issues.length > 0 && !save.error && (
              <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  <div className="min-w-0">
                    <p className="font-medium">
                      Fix {issues.length === 1 ? "this" : `these ${issues.length}`} before saving
                    </p>
                    <ul className="mt-1 space-y-0.5">
                      {issues.map((issue, i) => (
                        <li key={`${issue.path}-${i}`}>
                          <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => reveal(fieldId(issue.path))}>
                            <span className="font-medium">{issue.path.startsWith("metadata.") ? issue.path.slice(9).replace(/^\w/, (c) => c.toUpperCase()) : pathLabel(issue.path)}</span>
                            : {issue.message}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {catalogError && <ProblemList error={catalogError} title="The machine-config catalogue could not be read: configs are not checked, and new nodepools start empty" />}
            {schemaError && <ProblemList error={schemaError} title="The cluster template's inputs could not be read: the other template inputs are not shown" />}
          </div>
        )}

        {SECTIONS.map((section, index) => (
          <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`} className="scroll-mt-20 space-y-4">
            <SectionHeader step={index + 1} title={section.title} description={section.description} id={`${section.id}-title`} />
            <div className="rounded-2xl border bg-card p-5 shadow-card sm:p-6">
              {section.id === "basics" && (
                <BasicsSection
                  draft={draft}
                  isNew={isNew}
                  problems={problemsAt}
                  showNameProblems={attempted}
                  otherInputs={otherTop}
                  notEnforced={notEnforced}
                  onName={(name) => update((d) => ({ ...d, name }))}
                  onVersion={(version) => update((d) => ({ ...d, version }))}
                  onDescription={(description) => update((d) => ({ ...d, description }))}
                  onValue={(key, value) => update((d) => setTopValue(d, key, value))}
                  onLocked={(path, locked) => update((d) => setLocked(d, path, locked))}
                />
              )}
              {section.id === "nodepools" && (
                <NodepoolsSection
                  draft={draft}
                  update={update}
                  catalog={catalog}
                  catalogLoading={catalogLoading}
                  defaults={defaults}
                  schema={schema ?? []}
                  problems={problemsAt}
                  configProblems={configProblemsAt}
                  notEnforced={notEnforced}
                />
              )}
              {section.id === "addons" && <AddonsSection addons={draft.addons} onChange={(addons) => update((d) => ({ ...d, addons }))} />}
              {section.id === "review" && (
                <ReviewSection draft={draft} name={document.metadata.name} yaml={yaml} saved={spec ?? null} schema={schema} template={template} lines={lines} />
              )}
            </div>
          </section>
        ))}
      </div>

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        size="lg"
        title={isNew ? `Review: create flavor "${document.metadata.name}"` : `Review: update flavor "${document.metadata.name}"`}
        description={
          isNew
            ? "The flavor below is proposed as a new file in the specs repo, in a merge request another admin approves."
            : diff
              ? "The changed lines are highlighted. The change is proposed in a merge request another admin approves."
              : "Nothing changed."
        }
        diff={diff || undefined}
        onConfirm={() => save.mutate()}
        isPending={save.isPending}
        confirmLabel={isNew ? "Confirm — Create Flavor MR" : "Confirm — Update Flavor MR"}
        confirmDisabled={!diff}
      >
        {!diff && <p className="py-4 text-center text-sm italic text-muted-foreground">Nothing changed.</p>}
      </ReviewDialog>
    </div>
  );
}

/** Why a save did not go through, at the top; a 422's problems that have a field are shown there instead. */
function SaveProblems({
  error,
  unmatched,
  routed,
  name,
  onReload,
}: {
  error: unknown;
  unmatched: string[];
  routed: number;
  name: string;
  onReload?: () => void;
}) {
  if (isApiError(error, "REVISION_CONFLICT")) {
    return (
      <div className="space-y-2">
        <ProblemList error={error} title="This flavor changed since you opened it. Reload it and make your edits again." />
        {onReload && (
          <Button variant="outline" size="sm" onClick={onReload}>
            <RotateCcw /> Reload flavor
          </Button>
        )}
      </div>
    );
  }
  if (isApiError(error, "ALREADY_EXISTS")) {
    return (
      <div className="space-y-2">
        <ProblemList error={error} title={`A flavor named "${name}" already exists. Pick another name, or edit that flavor.`} />
        <Link href={`/specs/${encodeURIComponent(name)}`} className="text-sm text-primary hover:underline">
          Open the existing flavor
        </Link>
      </div>
    );
  }
  if (isApiError(error, "VALIDATION_ERROR")) {
    const title = (error as ApiError).message;
    const lines = [...unmatched];
    if (routed > 0) lines.push(routed === 1 ? "One more is shown at its field below." : `${routed} more are shown at their fields below.`);
    return <ProblemList error={error} lines={lines.length > 0 ? lines : errorMessages(error)} title={title} />;
  }
  return <ProblemList error={error} title={writeErrorTitle(error, "The flavor was not saved")} />;
}
