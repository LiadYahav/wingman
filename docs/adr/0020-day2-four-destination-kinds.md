# ADR-0020: day2 models four destination kinds, discovered from folders and day1, each with an id that carries its position

Date: 2026-11-07
Status: Accepted; amended 2026-11-13 (the web's Destinations page is removed; the API and the concept stay)

## Context

The legacy day2 service assumed the pre-Phase-C layout
`mces/<mce>/<cluster>/<addon>` and addressed a cluster as `(mce, cluster)`.
The gitops-day2 platform now has four destination kinds, each with its own
folder, Argo instance, version source and value stack (`docs/ecosystem/notes/day2-kubevirt.md` §1):

| Kind | Team repo folder | OCP version from | Leaf apps live on |
|---|---|---|---|
| hub | `defaults/hub/<chart>/` | none | prod-hub's Argo |
| mce | `sites/<site>/<env>/mces/<mce>/in-cluster/<chart>/` | day1 `sites/<site>/mces/<mce>/version.yaml` | the MCE's Argo |
| hosted | `sites/<site>/<env>/mces/<mce>/<cluster>/<chart>/` | day1 `.../hostedClusters/<cluster>.yaml` `mastertag` | the MCE's Argo |
| upi | `sites/<site>/<env>/upi/<cluster>/<chart>/` | optional `version.yaml` in that folder, per team | prod-hub's UPI Argo |

The platform registers nothing: a folder existing is the registration, `env`
and `site` are read off the path, and the day1 repo (read-only for day2)
knows MCEs and hosted clusters no team repo places yet.

## Decision

- `wingman_day2.domain.platform` simulates the ApplicationSet chain: per team
  repo, the destinations (`directories:` generators, one segment per `*`,
  hidden folders skipped) and the apps on each (own chart folders plus the
  fleet defaults of that kind minus `exclusions.yaml`). A destination whose
  required version is missing renders nothing, as the templates' `required`
  makes it.
- Discovery (`application/topology.py`) joins every team repo with day1. A
  day1 cluster no team places gets the env of its MCE's folder in any team
  repo, else the one its name carries (`ocp4-<env>-...`), else none; a
  cluster with no env is listed with a warning and cannot be written to.
- A cluster is a `ClusterRef(kind, name, site, env, mce)` with a stable id:
  `hub`, `mce:<site>:<env>:<mce>`, `hosted:<site>:<env>:<mce>:<cluster>`,
  `upi:<site>:<env>:<cluster>`. The API takes the id, or a bare name when it
  names exactly one destination (names are global in the platform); the
  legacy `?mce=` narrows a bare name.

## Alternatives rejected

- **Name-only addressing.** Names are meant to be global, but a misplaced
  folder makes two destinations share one; the id says which, and a write
  builds its path from the id without guessing.
- **Separate path templates per kind in settings** (the legacy
  `DAY2_*_PATH_TEMPLATE`). The layout is the platform's contract, not a
  deployment choice; `wingman_day2.domain.layout` is the one place it lives.

## Consequences

- A UPI cluster's version is per team (each team's own `version.yaml`), so
  two teams may render one UPI cluster at different versions; the cluster
  list reports a version only when they agree.
- The web app must switch from `(name, mce)` to the id; bare names keep the
  existing pages working for unambiguous clusters
  (`docs/notes/2026-11-07-day2-api-changes.md`).

## Verification

- `apps/day2-service/tests/oracle/test_render_chain_oracle.py`: the apps and
  destinations match `render_chain.py` for every fixture team (ADR-0021).
- `tests/unit/domain/test_clusters.py`: ids round-trip (hypothesis), shapes,
  Argo instance and fleet scope per kind.
- `tests/unit/application/test_reads.py`: discovery, env resolution,
  ambiguity, unknown env.

## Amendment (2026-11-13): the Destinations page is removed

The user removed the web's **Destinations** page (`/destinations`, one table
of every destination, each linking to its charts) and its sidebar entry: it
repeated what other pages do. A hosted cluster's charts are on its page; an
add-on's page on Addons has its defaults per scope, the destinations each
reaches, the values per env and per destination, and Deploy on specific MCEs
(ADR-0053's amendments). `/destinations` redirects to `/clusters`
(`next.config.ts`, 307). A destination's charts page leads back to its
cluster's page for a hosted cluster in day1, to `/clusters` for any other
hosted cluster, and to `/addons` for the hub, an MCE or a UPI cluster.

Unchanged: the four kinds, the ids, `GET /api/day2/clusters` and
`GET /api/day2/clusters/{id}` (a bare name with several candidates still
lists them), and every charts page at `/clusters/<id>/addons`.

The way in to a charts page that is not a hosted cluster's: an add-on's page
links each destination it names (the rows per scope, Deploy on specific MCEs,
the other UPI clusters). The hub is not named there, so its charts page is
linked only from a lint finding that names it.

Pinned by `apps/web/e2e/tests/day2-charts.spec.ts` (the redirect, the back
links), `page-states-day2.spec.ts` and `addon-defaults.spec.ts` (an MCE's
name opens its charts page).
