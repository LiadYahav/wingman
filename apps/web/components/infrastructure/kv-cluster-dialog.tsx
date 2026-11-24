"use client";

import { useState } from "react";
import Link from "next/link";
import { Copy, Loader2 } from "lucide-react";
import { ProvisionRunPanel } from "@/components/clusters/provision-run";
import { ProblemList } from "@/components/common/problem-list";
import { buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api-client";
import { MAX_KV_WORKERS } from "@/lib/kv-clusters";
import type { KvChoices, KvDraft, ProvisionRun } from "@/types";
import { KvClusterFields, OWNER_KEYS, type Owner } from "./kv-cluster-fields";
import { useCreateKvCluster, useKvDraft } from "./use-kv-cluster";

/** Where the dialog starts: a zone (the warning's) and the workers (the standby size). */
export interface KvDialogStart {
  zone: string | null;
  workers: number;
}

const NO_OWNER: Owner = { merkaz: "", anaf: "", mador: "" };

/** The typed workers as a number the draft takes, else `null`. */
function workersOf(text: string): number | null {
  const n = Number(text);
  return /^\d+$/.test(text.trim()) && n >= 1 && n <= MAX_KV_WORKERS ? n : null;
}

/** What the model gives, or that there is none. */
function ModelLine({ draft }: { draft: KvDraft }) {
  if (draft.model === null) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="kv-draft-model">
        No KV cluster exists to copy: give the owner. The file gets no machine configs and no tuning profiles.
      </p>
    );
  }
  const { name, configs, tuning_config: tuning } = draft.model;
  const tuned = Array.isArray(tuning) ? tuning.join(", ") : tuning;
  return (
    <p className="text-xs text-muted-foreground" data-testid="kv-draft-model">
      <Copy aria-hidden className="mr-1 inline h-3 w-3 align-[-2px]" />
      The same as <span className="font-mono text-foreground">{name}</span>: its owner,
      {configs.length > 0 ? ` its ${configs.length} machine configs` : " no machine configs"}
      {tuned ? ` and tuning ${tuned}` : ""}.
    </p>
  );
}

/** After the start: the run, then what follows the merge. */
function Created({ run, site }: { run: ProvisionRun; site: string }) {
  return (
    <div className="grid gap-4" data-testid="kv-created">
      <ProvisionRunPanel started={run} />
      <section className="rounded-xl border p-4 text-sm" aria-labelledby="kv-after-merge">
        <h3 id="kv-after-merge" className="font-semibold">After the merge</h3>
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-muted-foreground">
          <li>
            Install the <span className="font-mono text-foreground">vm-lifecycle-worker</span> add-on on it through day2,
            from its <Link href={`/clusters/${encodeURIComponent(run.cluster)}/addons`} className="text-primary hover:underline" data-testid="kv-after-addons">add-ons page</Link>:
            {" "}<span className="font-mono">kvCluster</span> {run.cluster}, <span className="font-mono">site</span> {site},{" "}
            <span className="font-mono">vlanId</span> the segment the run reserves, <span className="font-mono">vmMacPrefix</span>{" "}
            <span className="font-mono">0e</span> and that VLAN.
          </li>
          <li>
            Turn on bin-packing on its nodes: the descheduler&apos;s <span className="font-mono">HighNodeUtilization</span>{" "}
            compaction, so VMs fill few hypervisors.
          </li>
        </ol>
      </section>
    </div>
  );
}

/**
 * Create a KV cluster on a seed (ADR-0069): no form to fill, the draft is
 * the whole file, and an admin may change only the zone, the version, the
 * InfraEnv and the workers. Create starts provision-cluster with exactly the
 * draft's file and the name it showed; the run then shows as a tenant
 * create's does. Mount it while open: its state is one create's.
 */
export function KvClusterDialog({ seed, start, onClose }: { seed: string; start: KvDialogStart; onClose: () => void }) {
  const [zone, setZone] = useState<string | null>(start.zone);
  const [mastertag, setMastertag] = useState<string | null>(null);
  const [infraEnv, setInfraEnv] = useState<string | null>(null);
  const [workersText, setWorkersText] = useState(String(start.workers));
  const [owner, setOwner] = useState<Owner>(NO_OWNER);
  const workers = workersOf(workersText);
  const ownerGiven = OWNER_KEYS.every((key) => /^\d{1,10}$/.test(owner[key]));
  const choices: KvChoices = { zone, mastertag, infra_env: infraEnv, workers: workers ?? start.workers, owner: ownerGiven ? owner : null };
  const draft = useKvDraft(seed, choices);
  const create = useCreateKvCluster(seed);
  const pending = create.isPending;
  const settled = isApiError(create.error, "AMBIGUOUS_WRITE");
  const shown = draft.data;
  const ready = Boolean(shown?.yaml && shown.name) && workers !== null && !draft.isPlaceholderData;
  const canCreate = ready && !pending && !settled && !create.data;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canCreate || !shown?.name) return;
    const { name, zone: z, infra_env, mastertag: tag } = shown;
    create.mutate({ name, zone: z, infra_env, mastertag: tag, workers: workers ?? shown.workers, owner: shown.model ? null : owner });
  };
  const chooseZone = (next: string | null) => {
    setZone(next);
    setInfraEnv(null);
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto" showCloseButton={false} data-testid="kv-cluster-dialog">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Create a KV cluster</DialogTitle>
            <DialogDescription>
              On <span className="font-mono">{seed}</span>, the same as the KV clusters before it, through the platform&apos;s
              provision-cluster workflow: it reserves the segment and opens the merge request.
            </DialogDescription>
          </DialogHeader>
          {create.data ? (
            <Created run={create.data} site={shown?.site ?? ""} />
          ) : draft.isLoading ? (
            <div className="grid gap-2"><Skeleton className="h-5 w-64" /><Skeleton className="h-40 w-full" /></div>
          ) : draft.error ? (
            <ProblemList error={draft.error} title="The draft could not be read" />
          ) : shown ? (
            <>
              <KvClusterFields
                draft={shown} zone={zone} mastertag={mastertag} infraEnv={infraEnv} workers={workersText} owner={owner}
                onZone={chooseZone} onMastertag={setMastertag} onInfraEnv={setInfraEnv} onWorkers={setWorkersText} onOwner={setOwner}
                disabled={pending || settled}
              />
              <ModelLine draft={shown} />
              {workers === null && <ProblemList lines={[`Workers are 1 to ${MAX_KV_WORKERS}.`]} title="Not ready to create" />}
              {shown.problems.length > 0 && <ProblemList lines={shown.problems} title="Not ready to create" />}
              {shown.yaml && (
                <div className="grid gap-1">
                  <span className="text-xs font-medium text-muted-foreground">
                    The file, <span className="font-mono">{shown.path}</span>
                  </span>
                  <pre data-testid="kv-draft-yaml" className="max-h-64 overflow-auto rounded-lg border bg-muted/30 px-3 py-2 font-mono text-xs">{shown.yaml}</pre>
                </div>
              )}
            </>
          ) : null}
          {Boolean(create.error) && (
            <div data-testid="kv-create-error">
              <ProblemList
                error={create.error}
                title={settled ? "No answer: the run may have started. Look at Approvals before sending again." : "Not started."}
              />
            </div>
          )}
          <DialogFooter>
            <button type="button" onClick={onClose} disabled={pending} className={buttonVariants({ variant: "outline" })}>
              {create.data || settled ? "Close" : "Cancel"}
            </button>
            {!create.data && (
              <button type="submit" disabled={!canCreate} className={buttonVariants({ variant: "default" })} data-testid="kv-create">
                {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
                {pending ? "Starting…" : "Create"}
              </button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
