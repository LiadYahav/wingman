/**
 * The day1 service as the web calls it (ADR-0056, web rule 2): `day1Api`,
 * typed calls by area, and `day1Keys`, the query keys. Pages, components and
 * hooks name no `/api/day1` path and spell no key themselves.
 *
 * One file per area, each under the size limit: clusters.ts (a cluster's file
 * and its reads) and cluster-workflows.ts (the workflows day1 starts on it)
 * are both `day1Api.clusters`. The review and audit routes cover day2's MRs
 * too (approvals.ts says why). The calls answer what day1 answers: a page
 * keeps its own handling of a 501 FEATURE_DISABLED or a 404.
 */

import { approvalsApi } from "./approvals";
import { auditApi } from "./audit";
import { authApi, serviceBuild } from "./auth";
import { clusterWorkflowsApi } from "./cluster-workflows";
import { clustersApi } from "./clusters";
import { fleetApi } from "./fleet";
import { specsApi } from "./specs";

export const day1Api = {
  auth: authApi,
  build: serviceBuild,
  clusters: { ...clustersApi, ...clusterWorkflowsApi },
  specs: specsApi,
  approvals: approvalsApi,
  audit: auditApi,
  fleet: fleetApi,
};

export { day1Keys } from "./keys";
