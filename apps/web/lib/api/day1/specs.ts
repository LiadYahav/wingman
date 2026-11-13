/**
 * day1's flavor routes (`/api/day1/specs`; the UI says Flavor, the API keeps
 * `/specs`): the shared template, each flavor, its clusters, drift, history,
 * rollout (ADR-0044) and the import of existing clusters. A write is guarded
 * by the `last_commit_id` the flavor was read at, when the read gave one
 * (ADR-0006).
 */

import { api } from "@/lib/api-client";
import type {
  ClusterSpec,
  ImportPreview,
  ImportPreviewRequest,
  ImportRequest,
  ImportResult,
  MRDetail,
  RolloutStatus,
  SpecCluster,
  SpecCommit,
  SpecDetail,
  SpecDrift,
  SpecEntry,
  TemplateField,
} from "@/types";

const SPECS = "/api/day1/specs";

const specPath = (name: string) => `${SPECS}/${encodeURIComponent(name)}`;

/** `/api/day1/specs/{name}`, with `?last_commit_id=` when the read gave one. */
const guarded = (name: string, lastCommitId?: string | null) =>
  lastCommitId ? `${specPath(name)}?last_commit_id=${encodeURIComponent(lastCommitId)}` : specPath(name);

export const specsApi = {
  list: () => api.get<SpecEntry[]>(SPECS),
  /** The template's inputs, parsed by day1 from the Jinja2 AST. */
  templateSchema: () => api.get<TemplateField[]>(`${SPECS}/template/schema`),
  /** The shared template's text, as a JSON string. */
  sharedTemplate: () => api.get<string>(`${SPECS}/template`),
  get: (name: string) => api.get<SpecDetail>(specPath(name)),
  create: (document: ClusterSpec) => api.post<MRDetail>(SPECS, document),
  update: (name: string, lastCommitId: string | null | undefined, document: ClusterSpec) =>
    api.put<MRDetail>(guarded(name, lastCommitId), document),
  /** A flavor that does not load has no commit to send. */
  remove: (name: string, lastCommitId?: string | null) => api.del<MRDetail>(guarded(name, lastCommitId)),
  clusters: (name: string) => api.get<SpecCluster[]>(`${specPath(name)}/clusters`),
  drift: (name: string) => api.get<SpecDrift[]>(`${specPath(name)}/drift`),
  history: (name: string) => api.get<SpecCommit[]>(`${specPath(name)}/history`),
  /** The flavor file at a commit, as text. */
  atSha: (name: string, sha: string | null) => api.getText(`${specPath(name)}/at/${sha}`),
  rollout: (name: string) => api.get<RolloutStatus>(`${specPath(name)}/rollout`),
  /** Reconcile now: open the cluster MRs that are due. */
  reconcileRollout: (name: string) => api.post<RolloutStatus>(`${specPath(name)}/rollout`),
  importPreview: (name: string, body: ImportPreviewRequest) =>
    api.post<ImportPreview>(`${specPath(name)}/import/preview`, body),
  /** One MR per cluster (ADR-0044). */
  importClusters: (name: string, body: ImportRequest) => api.post<ImportResult>(`${specPath(name)}/import`, body),
};
