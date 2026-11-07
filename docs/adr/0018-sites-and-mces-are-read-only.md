# ADR-0018: Sites and MCEs are read-only folders in Wingman

Date: 2026-11-07
Status: Accepted

## Context

The legacy service created a site or an MCE by opening an MR that added a
`.gitkeep` (`sites/<site>/.gitkeep`, `.../mces/<mce>/hostedClusters/.gitkeep`).
An empty file in `hostedClusters/` breaks that MCE's ApplicationSet
(ADR-0012). And a folder does not make an MCE: it needs a hub Argo cluster
secret named like the folder, its own GitOps operator with repo
credentials, and herzi. The user decided on 2026-11-07 that Wingman never
creates sites or MCEs; onboarding happens elsewhere.

## Decision

- Sites are the folders under `sites/`; MCEs the folders under
  `sites/<site>/mces/`. Wingman lists them from one recursive tree read and
  never writes them. `POST /api/day1/sites` and
  `POST /api/day1/sites/{site}/mces` are removed (405).
- `GET /api/day1/mces` shows, per MCE, its default `mastertag` for hosted
  clusters (its `values.yaml`), the hub's own version (`version.yaml`),
  whether its name follows the convention, its cluster count and any stray
  files in `hostedClusters/`.
- A cluster can be created only under an MCE folder that exists.

## Alternatives rejected

- **Keep create, without `.gitkeep`** (write `values.yaml` instead): still
  a half-onboarded MCE that ArgoCD cannot reach.

## Consequences

- The web form's "Create new…" options for site and MCE must go (listed in
  `docs/notes/2026-11-07-day1-api-changes.md`).
- When sites come from segments-manager or server-scan (phase 1 of the
  ecosystem plan), the source changes here, still read-only.

## Verification

The 405 regression test and the MCE view tests in
`apps/day1-service/tests/api/test_problems_and_rbac.py` and
`apps/day1-service/tests/api/test_cluster_lifecycle.py`.
