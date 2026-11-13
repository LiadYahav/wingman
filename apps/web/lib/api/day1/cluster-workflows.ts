/**
 * The platform workflows day1 starts on a cluster, and what they act on:
 * provision-cluster (ADR-0042), delete-cluster (ADR-0033), a node's
 * uninstall from its NodePool (ADR-0038) and upgrade-cluster (ADR-0055).
 * Wingman starts a run and shows it; the procedure is the workflow's. A
 * start is never retried (ADR-0006).
 *
 * `where` is the `?site=&mce=` query the cluster page reads the cluster with.
 */

import { api } from "@/lib/api-client";
import type {
  ClusterNodes,
  DeleteWorkflowState,
  ProvisionRun,
  Provisioner,
  StartUpgradeRequest,
  UninstallNodeRequest,
  UpgradeDecision,
  UpgradeDecisionRequest,
  UpgradeDecisionResult,
  UpgradeRun,
  UpgradeTargets,
  WorkflowRun,
} from "@/types";
import { CLUSTERS, clusterPath } from "./clusters";

const deleteWorkflowPath = (name: string, where: string) => `${clusterPath(name)}/delete-workflow${where}`;
const upgradeRunPath = (name: string) => `${clusterPath(name)}/upgrade-run`;

export const clusterWorkflowsApi = {
  /** What Create does in this deployment. */
  provisioner: () => api.get<Provisioner>(`${CLUSTERS}/provisioner`),
  provisionRun: (name: string) => api.get<ProvisionRun>(`${clusterPath(name)}/provision-run`),
  /** 501 FEATURE_DISABLED until the delete-cluster workflow exists. */
  deleteWorkflow: (name: string, where: string) => api.get<DeleteWorkflowState>(deleteWorkflowPath(name, where)),
  startDeleteWorkflow: (name: string, where: string) =>
    api.post<WorkflowRun>(deleteWorkflowPath(name, where), { confirm: true }),
  /** The nodes by NodePool (501 FEATURE_DISABLED when day1 cannot read the MCE). */
  nodes: (name: string, where: string) => api.get<ClusterNodes>(`${clusterPath(name)}/nodes${where}`),
  uninstallNode: (name: string, serverId: string, where: string, body: UninstallNodeRequest) =>
    api.post<WorkflowRun>(`${clusterPath(name)}/nodes/${encodeURIComponent(serverId)}/uninstall${where}`, body),
  upgradeRun: (name: string, where: string) => api.get<UpgradeRun>(`${upgradeRunPath(name)}${where}`),
  /** Starts a short run of the workflow: it can take up to a minute. */
  upgradeTargets: (name: string, where: string) =>
    api.get<UpgradeTargets>(`${clusterPath(name)}/upgrade-targets${where}`),
  startUpgrade: (name: string, where: string, body: StartUpgradeRequest) =>
    api.post<UpgradeRun>(`${clusterPath(name)}/upgrade${where}`, body),
  decideUpgrade: (name: string, where: string, decision: UpgradeDecision, body: UpgradeDecisionRequest) =>
    api.post<UpgradeDecisionResult>(`${upgradeRunPath(name)}/${decision}${where}`, body),
  /** An agent's proposal, approved or rejected. */
  decideUpgradeAction: (name: string, where: string, actionId: string, approve: boolean) =>
    api.post<UpgradeDecisionResult>(
      `${upgradeRunPath(name)}/actions/${encodeURIComponent(actionId)}/${approve ? "approve" : "reject"}${where}`
    ),
};
