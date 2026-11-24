/**
 * The day1 service as the web calls it (ADR-0056, web rule 2): `day1Api`,
 * typed calls by area, and `day1Keys`, the query keys. Pages, components and
 * hooks name no `/api/day1` path and spell no key themselves.
 *
 * One file per area, each under the size limit: clusters.ts (a cluster's file
 * and its reads), cluster-workflows.ts (the workflows day1 starts on it) and
 * scale.ts (its NodePools through update-nodepool) are all `day1Api.clusters`;
 * seeds.ts is a seed's next KV cluster (ADR-0069).
 * The review and audit routes cover day2's MRs too (approvals.ts says why).
 * The calls answer what day1 answers: a page keeps its own handling of a 501
 * FEATURE_DISABLED or a 404.
 */

import { approvalsApi } from "./approvals";
import { auditApi } from "./audit";
import { authApi, serviceBuild } from "./auth";
import { clusterWorkflowsApi } from "./cluster-workflows";
import { clustersApi } from "./clusters";
import { fleetApi } from "./fleet";
import { scaleApi } from "./scale";
import { seedsApi } from "./seeds";
import { specsApi } from "./specs";

export const day1Api = {
  auth: authApi,
  build: serviceBuild,
  clusters: { ...clustersApi, ...clusterWorkflowsApi, ...scaleApi },
  specs: specsApi,
  approvals: approvalsApi,
  audit: auditApi,
  fleet: fleetApi,
  seeds: seedsApi,
};

export { day1Keys } from "./keys";
