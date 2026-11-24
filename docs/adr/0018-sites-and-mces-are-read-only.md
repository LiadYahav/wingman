# ADR-0018: Sites and MCEs are read-only folders in Wingman

Date: 2026-11-07
Status: Accepted; amended 2026-11-24: Customer MCEs' Create MCE is a preview of the vision that writes nothing (see the amendment)

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

## Amendment (2026-11-24): a Create MCE preview, which writes nothing

The user asked for "a Create New MCE button (which won't work now but will
show the vision)". Wingman still never creates a site or an MCE: the
Decision above holds.

1. **Customer MCEs has Create MCE** (admins only, as the whole
   Infrastructure workspace, ADR-0067), marked Preview on the button and in
   the dialog. It shows what creating a Customer MCE will ask for and do, on
   the platform's design (`docs/ecosystem/notes/kubevirt-platform.md` §1, §2
   and §7): the tenants' hub for one OpenShift version band, a standalone
   cluster on KubeVirt VMs, one master VM per zone (AD19) and the workers
   spread over the zones (AD20), every VM a `kv32` (32 vCPU, 128 GiB).
2. **Its inputs work**: the site (the day1 repo's), the lifecycle (`prod`,
   `prep`, `test`), the OpenShift version and the workers per zone. The
   name, `ocp4-<lifecycle>-mce-<site>-<id>` with `<id>` the next letter no
   Customer MCE at the site has, the zones (the site's seeds'; a site
   without one is told it needs a seed per zone first), the VMs and the
   steps follow them: create the VMs (create-vm, labelled
   `redbull.io/role=mce` and `redbull.io/mce=<name>`), install the cluster
   (every Node labelled with its zone), install MCE with HyperShift, add
   the day1 folder `sites/<site>/mces/<name>/` (`values.yaml`,
   `version.yaml`), then herzi fills its InfraEnv pools and placement may
   pick it. The platform's acceptance test P11 is listed as what "done"
   means. Everything is worked out in the browser from the MCE list the
   page already reads (`apps/web/lib/mce-preview.ts`).
3. **Create is disabled** with its reason, said on the dialog and as the
   button's description: "Not available yet: a Customer MCE is installed by
   hand today (the platform's procedure 12); no workflow creates one." The
   preview calls no API and writes nothing; day1 has no MCE create, and
   `POST /api/day1/sites/{site}/mces` stays a 405.
4. **If a workflow comes to create Customer MCEs**, Create would start it,
   as every cluster create starts provision-cluster (ADR-0042): Wingman
   triggers the workflow and shows its run, and writes no MCE folder
   itself. That needs its own ADR.

Verification: `apps/web/lib/mce-preview.test.ts` (the name's letter, a
site's zones, the VMs) and `apps/web/e2e/tests/customer-mces.spec.ts`
(the inputs drive the name, zones and steps; Create is disabled with its
reason; no request but a read is sent).
