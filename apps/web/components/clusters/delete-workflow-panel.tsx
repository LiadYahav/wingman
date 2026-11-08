"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Workflow } from "lucide-react";
import { api, isApiError } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";
import { buttonVariants } from "@/components/ui/button";
import { ProblemList } from "@/components/common/problem-list";
import type { DeleteWorkflowState, WorkflowRun } from "@/types";

/** What the delete-cluster workflow does, in its order (docs/ideas/architecture-fit.md). */
const STEPS = [
  "Drain the cluster's workloads",
  "Remove the cluster's files (one commit, merged by a person)",
  "Wait for ArgoCD to remove every resource",
  "Wait for the released nodes to be wiped and returned to their pool",
  "Delete the DHCP scope",
  "Release the network segment",
];

type Availability =
  | { available: false; detail: string }
  | { available: true; run: WorkflowRun | null };

/**
 * The delete-cluster workflow (ADR-0033). Until it exists, day1 answers 501
 * FEATURE_DISABLED and this shows "Not available yet" with what the workflow
 * will do. When it exists, the same panel starts it and shows the run, with
 * no change here.
 */
export function DeleteWorkflowPanel({
  name,
  where,
  isAdmin,
}: {
  name: string;
  /** The `?site=&mce=` query the cluster page reads the cluster with. */
  where: string;
  isAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const path = `/api/day1/clusters/${encodeURIComponent(name)}/delete-workflow${where}`;
  const queryKey = ["clusters", name, "delete-workflow"];
  const [typed, setTyped] = useState("");

  const { data, isLoading, error } = useQuery<Availability>({
    queryKey,
    queryFn: async () => {
      try {
        const state = await api.get<DeleteWorkflowState>(path);
        return { available: true, run: state.run };
      } catch (e) {
        if (isApiError(e, "FEATURE_DISABLED")) return { available: false, detail: e.message };
        throw e;
      }
    },
    retry: false,
  });

  const start = useMutation({
    mutationFn: () => api.post<WorkflowRun>(path, { confirm: true }),
    onSuccess: (run) => {
      toast.success(`Delete workflow started: ${run.workflow_id}`);
      queryClient.invalidateQueries({ queryKey });
    },
    onError: (e) => toast.error(`The delete workflow did not start: ${e.message}`),
  });

  if (isLoading) return <Skeleton className="h-28 w-full" />;
  if (error) return <ProblemList error={error} title="The delete workflow's state could not be read" />;
  if (!data) return null;

  const run = data.available ? data.run : null;
  const canStart = data.available && isAdmin && !run && typed === name && !start.isPending;

  return (
    <section
      aria-label="Delete-cluster workflow"
      data-testid="delete-workflow"
      className="rounded-lg border bg-muted/30 p-4 text-sm space-y-3"
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 font-medium">
          <Workflow className="h-4 w-4 text-muted-foreground" />
          Delete-cluster workflow
        </div>
        {!data.available && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            Not available yet
          </span>
        )}
      </div>

      {!data.available && <p className="text-xs text-muted-foreground">{data.detail}</p>}

      <ol className="list-decimal pl-5 text-xs text-muted-foreground space-y-0.5">
        {STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>

      {run ? (
        <div className="rounded-md border bg-background p-3 text-xs space-y-1" data-testid="delete-workflow-run">
          <p className="font-mono break-all">{run.workflow_id}</p>
          <p>
            <span className="font-medium">{run.status}</span>
            {run.phase && <span className="text-muted-foreground"> · {run.phase}</span>}
          </p>
          {run.error && <p className="text-status-error-fg break-words">{run.error}</p>}
        </div>
      ) : (
        isAdmin && (
          <div className="space-y-2">
            {data.available && (
              <label className="block text-xs text-muted-foreground">
                Type <span className="font-mono text-foreground">{name}</span> to confirm; this cannot be undone.
                <input
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  aria-label="Cluster name, to confirm the delete workflow"
                  className="mt-1 w-full rounded-md border bg-background px-2.5 py-1.5 font-mono text-xs"
                />
              </label>
            )}
            <button
              type="button"
              disabled={!canStart}
              onClick={() => start.mutate()}
              className={buttonVariants({ size: "sm", variant: "destructive" })}
            >
              Start delete workflow
            </button>
          </div>
        )
      )}
    </section>
  );
}
