// ── The delete-cluster workflow (ADR-0033) ──────────────────────────────────

/** One run of a workflow that acts on a cluster, as the orchestrator reports it. */
export interface WorkflowRun {
  workflow_id: string;
  /** The orchestrator's status, lowercase: `running`, `completed`, `failed`, ... */
  status: string;
  /** The step it is on, for example `awaiting-prune`. */
  phase: string | null;
  error: string | null;
}

/**
 * A provision-cluster run (ADR-0042): `POST /clusters` in workflow mode (202),
 * and `GET /clusters/{name}/provision-run`. The phase is the workflow's own
 * word; Wingman keeps no list of them.
 */
export interface ProvisionRun extends WorkflowRun {
  /** The new cluster file's stem. */
  cluster: string;
  /** The merge request the workflow opened, once it has. */
  merge_request_url: string | null;
  merge_request_state: string | null;
}

/** `GET /clusters/provisioner`: what Create does in this deployment. */
export interface Provisioner {
  mode: "merge-request" | "workflow";
}

/** `GET /clusters/{name}/delete-workflow` (501 FEATURE_DISABLED until the workflow exists). */
export interface DeleteWorkflowState {
  run: WorkflowRun | null;
}
