# kubevirt-workflows: the KubeVirt platform's model, names and procedures, for Wingman

Repo: `github.com/Idan-Maimon/kubevirt-workflows`, `main` at **`3ba0835`** (2026-11-23,
"Add acceptance tests"). Read on 2026-11-23 from a shallow clone, read only; nothing in it was run.
Paths below are relative to that repo (`KVW`) or to this one (`WM`). It is the repo the 2026-10-22
reading at `f7b714e` covered ([day2-kubevirt.md](day2-kubevirt.md) §3): this note replaces that
section for everything KubeVirt. What Wingman must change for it is
[`../../ideas/kubevirt-seed-kv-readiness.md`](../../ideas/kubevirt-seed-kv-readiness.md).

**Which parts carry weight** (`KVW/docs/review/assessment-brief.md` §3.1, the architect's own
table): `docs/architecture.md` is the architect's and authoritative; `docs/naming-convention.md`
is the platform's naming source of truth since 2026-11-22 (PR #1, merged `5ffaca3`; out of draft
in `189cf8e`); `inventory-controller.md`, `kv-capacity-controller.md` and the `review/` files
were written with an AI assistant from the architect's decisions; `docs/procedures/` and
`docs/animations/` are AI drafts the architect has not reviewed, so where a procedure and the
architecture disagree, the procedure is more likely wrong. `workflow/`, `nodepools/` and `argocd/`
are a superseded prototype.

No secret is in the repo (`workflow/deploy/secret.example.yaml` is a template).
`docs/review/assessment-brief.md` §3.3 names a live sandbox address; it is not repeated here.

---

## 0. What changed since `f7b714e`

| Commits | What |
|---|---|
| `19b1ebb`, `8f6eae0` (11-15, 11-16) | AD21 to AD31: InfraEnv scope, machine objects outside Git, destroy-on-release, in-place upgrades, version skew, the KV capacity model; `kv-capacity-controller.md` |
| `e7cd669`, `8341622` (11-16) | `review/update-nodepool-assessment.md`: twelve findings on `team-redbull/workflows` `feat/update-nodepool` |
| `204279f`, `1349961`, `9b1f220`, `eb4738f` (11-17) | AD29, AD32, AD33 (one install workflow, placement serialised per zone, first fit); procedure 19 and the draft animation 20 (remove nodes: the customer picks, or any) |
| `ade1f04` to `76b1f61` (11-18, 11-19) | The naming draft: names, zones, labels, claimed Agents |
| `34753c6` (11-19) | `review/create-vm-plan-corrected.md`: the create-vm implementation plan, matched to the team's design |
| `b03ed1c`, `5ffaca3`, `189cf8e` (11-22) | The convention out of draft: the zone in seed and KV cluster names, no site in InfraEnv names |
| `9381d95`, `2f2a831`, `46a76c9` (11-22) | `vm-placement.md` deprecated (the design moved to the workflows repo); the MCE-and-tenant-VMs placement draft; the build-status diagram (`docs/status/components.json`) |
| `3ba0835` (11-23) | `Acceptance Tests/acceptance-tests.md`: provisioning P1-P11, modification M1-M18, upgrade U1-U7, deletion D1-D4 |

---

## 1. The model

Five layers (`assessment-brief.md` §2, `architecture.md` AD8, AD17-AD20, glossary):

| Layer | What it is | Installed by | Its control plane runs on |
|---|---|---|---|
| **Seed** | One bare-metal cluster per zone, running MCE and HyperShift. The zone's infrastructure management plane (AD17) | Hand, UPI (procedure 10) | Itself |
| **KV cluster** | A hosted cluster whose bare-metal workers run OpenShift Virtualization; where every VM runs. Single-zone (AD8). A **cell** is one KV cluster with its seed resources and pool | `provision-cluster` against the seed (AD27; procedure 06 is an older hand-run draft) | Its zone's seed (AD18) |
| **Customer MCE** | The tenant hub: MCE, HyperShift and the Agent installer, for one OCP **version band**. Itself on VMs: one master per zone (AD19), workers spread over zones (AD20) | Hand, UPI on VMs (procedure 12) | Itself |
| **Tenant hosted cluster** | A tenant's cluster: control plane as pods on a Customer MCE, workers drawn from pools, one NodePool per zone per node type (glossary "NodePool") | `provision-cluster` against the Customer MCE (procedure 03) | A Customer MCE |
| **Bare metal** | Physical servers, tracked by server-scan | Vendor tooling, `provision-dell-server` | — |

- **Tenant workers are Agents, VM or bare metal, on the Agent platform.** HyperShift's
  KubeVirt platform type ties a HostedCluster's NodePools to one KubeVirt cluster (C2), so the
  platform uses the Agent platform (AD3): `kubevirt-redfish` exposes each VM as a Redfish BMC,
  so MCE installs a VM exactly like a physical server, and one HostedCluster spans one KV cluster
  per zone (AD8). A KubeVirt-platform NodePool cannot mix with bare-metal Agents (C1).
- **A pool is one InfraEnv**: one server configuration (flavor), one size (`mtl` or `kv<cpu>`)
  and one zone, on one hub, shared by every consumer (AD21). A VM pool is tied to the hardware it
  was built on because a VM cannot live-migrate to an older CPU generation (C8).
- **Demand and supply are two loops** (`procedures/README.md` "The shape of it"): customers
  write NodePool totals in Git; the Inventory Controller (herzi, one per hub, Customer MCEs and
  seeds alike, `inventory-controller.md`) keeps each pool at demand plus a buffer. "A cluster
  can be created with no workers available."
- **A KV cluster is just a hosted cluster whose hub is the seed** (`procedures/README.md`, "KubeVirt
  clusters"): procedures 06 to 09 are 03, 04, 01, 02 and 05 with the seed as the hub, plus an
  evacuation where a hypervisor leaves (08, 09, 16).
- **Constraints that bound the rest:** a HostedCluster's NodePools cannot span hubs (C6); a hosted
  cluster may not run newer than its MCE supports (C3, C4), so a cluster that outgrows its band
  is rebuilt on another MCE (procedure 18); live migration needs shared storage (C7).

---

## 2. How it maps to day1 and to MCEs

The day1 values repo keeps its one shape, `sites/<site>/mces/<hub>/hostedClusters/<cluster>.yaml`,
and a **seed is a hub folder like an MCE's** (`review/create-vm-plan-corrected.md` decision 3,
"the hosted clusters of the site's seed folders (`sites/<site>/mces/<seed>/hostedClusters/`)";
acceptance test P1):

| Object | Its day1 place | Its hub | Created by |
|---|---|---|---|
| Customer MCE | the folder `sites/<site>/mces/ocp4-<lc>-mce-<site>-<id>/` | — (standalone) | Hand (12); Wingman never creates the folder (ADR-0018) |
| Tenant hosted cluster | `sites/<site>/mces/<mce>/hostedClusters/ocp4-<lc>-<flavor>-<site>-<id>.yaml` | its Customer MCE | `provision-cluster`, or Wingman's MR |
| Seed | the folder `sites/<site>/mces/ocp4-<lc>-seed-<site>-<zone>-<id>/` | — (standalone) | Hand (10). **"Its day1 folders do not exist yet"** (`docs/status/components.json`, Seed clusters) |
| KV cluster | `sites/<site>/mces/<seed>/hostedClusters/ocp4-<lc>-kv-<site>-<zone>-<id>.yaml` | its zone's seed | `provision-cluster`, started by the KV Capacity Controller (AD27) |

- **The cluster name's flavor tells them apart.** `mce`, `seed` and `kv` are reserved: "They are
  how a seed's folder and a KV cluster's file are told apart from an MCE's and a tenant's in day1"
  (`naming-convention.md` §1, "Cluster flavors"). No folder kind or marker file exists.
- A KV cluster's file is an ordinary values file. Its NodePools draw from the seed's
  bare-metal pools (`c200-mtl-az1`), and **every NodePool carries `nodeLabels:
  topology.kubernetes.io/zone: <zone>`, equal to the zone in the cluster's name** (§3 below). Its
  Argo CD Application runs on the seed, named after the file (P1, criteria 3-4).
- Per KV cluster, through **day2**, the `vm-lifecycle-worker` chart (`kvCluster` = the day1 file
  stem, `site`, `vlanId`, `vmMacPrefix` = `0e` + that VLAN; create-vm plan §1.5, §4 step 4;
  acceptance P1 criterion 6).
- A tenant cluster's NodePools are named `<cluster without ocp4->-<InfraEnv>`
  (`test-eck-five-a-c200-mtl-az1`), its namespace `hcp-<cluster without ocp4->`, its Argo
  Application the file stem (acceptance §3, the paragraph before P1): Wingman's production naming
  (ADR-0015).
- InfraEnv names carry no hub and no site, so **every hub at a site has the same pool names**
  (`c200-mtl-az1` on the Customer MCE and on the seed). A pool is always (hub, InfraEnv).

---

## 3. Zones

`naming-convention.md` §2-§3:

- **A server's zone is physical:** the Cisco ACI leaf it is cabled to. The convention makes
  server-scan its only source of truth, and a VM's zone its KV cluster's zone, which server-scan
  records when it scans the KV clusters. **server-scan has no zone field yet** (v6.9.2, `911d2c7`:
  none in its backend), although the status diagram lists "zone from the ACI leaf" under it.
- **The zone is not in a node's, a tenant cluster's or an MCE's name**; it is in InfraEnv, seed
  and KV cluster names. A recabled server changes zone without being renamed.
- **The draw filters by name and zone:** InfraEnv `<flavor>-<size>-<zone>` draws servers named
  `ocp-<flavor>-<size>-<site>-*` (site = its MCE's) whose server-scan zone is `<zone>`. Whether
  server-scan's availability query can filter by zone is open (§6 item 2). A VM needs no draw:
  `create-vm` builds it in the zone (AD29). After the Agent registers, the install checks
  server-scan's zone equals the InfraEnv's and rolls back if not (§3 rule 4).
- **Each zone's NodePool claims only its zone's Agents** (by the InfraEnv's labels, §4) and stamps
  `topology.kubernetes.io/zone` on its Nodes, so tenant workloads spread with
  `topologySpreadConstraints` (AD7).
- **KV clusters are single-zone**, and `create-vm` learns a KV cluster's zone only from its day1
  file's `nodeLabels`. A KV cluster file whose NodePools name no zone, or two, "is never offered
  to placement", so it is **refused when written**, by `provision-cluster` or day1 CI (§4.b; §6
  item 10; acceptance P1 criterion 5).
- **Customer MCE Nodes need the zone label too**, or HyperShift's required zone spread of a hosted
  control plane's etcd silently does nothing (§4.a table; `review/mce-vm-placement-draft.md` §2-§3,
  verified in HyperShift's `setMultizoneSpread`). How they get it is open (§6 item 7).

**Contradiction to raise:** `assessment-brief.md` §4 (2026-11-17) says "Zones are soft. A zone is a
label assigned by the InfraEnv an agent registers from, not a recorded physical location"; the
convention (2026-11-22) says the zone is physical, from the ACI leaf. The convention is newer.

---

## 4. Names and labels

The rules are [`naming-convention.md`](https://github.com/Idan-Maimon/kubevirt-workflows/blob/main/docs/naming-convention.md);
what Wingman needs from them:

| Object | Pattern (§1) | Example | Wingman today |
|---|---|---|---|
| Tenant cluster, MCE | `ocp4-<lifecycle>-<flavor>-<site>-<id>` | `ocp4-prod-eck-five-a`, `ocp4-prod-mce-five-a` | `ocp4-<env>-<name>-<site>[-<seq>]` (ADR-0014): `<seq>` optional, any flavor allowed |
| Seed, KV cluster | `ocp4-<lifecycle>-<seed\|kv>-<site>-<zone>-<id>` | `ocp4-prod-seed-five-az1-a`, `ocp4-prod-kv-five-az1-a` | Not modelled: both read as off-convention |
| Node (VM or bare metal) | `ocp-<flavor>-<mtl\|kv<cpu>>-<site>-<serial\|mac>` | `ocp-c200-mtl-five-fch2145v1ab`, `ocp-c200-kv32-five-02a1b2c3d4e5` | A pool's servers are `ocp-<infraEnv>…` (`WM/apps/day1-service/src/wingman_day1/domain/inventory.py`, `named_for`) |
| InfraEnv | `<flavor>-<mtl\|kv<cpu>>-<zone>` | `c200-mtl-az1`, `c200-kv32-az1` | Opaque names (only the prefix rule above) |

- `lifecycle` is `prod`, `prep` or `test`; `id` is one letter `a` to `z`; `kv<cpu>` is the VM's
  vCPU count; a node's last segment is a bare-metal serial or a VM's full 12-hex MAC (each KV
  cluster has its own MAC prefix, so a half MAC could repeat). Flavor variants: `n` (extra NIC),
  `d` (extra disk), `x` (to be defined). Everything lowercase.
- **Bare-metal node names are at most 32 characters** (Cisco UCS), so with an 11-character serial
  a site name is at most 6 characters (§1 "Length"; §6 item 8). VM names may use 63.
- **Older names elsewhere in the same repo are superseded** by the convention, and §6 item 11
  says architecture §9 is updated "once agreed": architecture §9 (`<env>-<site>[-<zone>]-<type><nn>`,
  InfraEnvs `conf203-zone-a-medium`), `inventory-controller.md` (`<server-type>[-<variant>]-<zone>-<size>`),
  `kv-capacity-controller.md` rule 6.4 (`<env>-<site>-<zone>-kv<nn>`), procedures 06, 10 and 12
  (`kv-<zone>-<cluster-id>`, `bm-<zone>`, sizes `32-128`), and the create-vm plan of 11-19
  (`<flavor>-kv<cpu>-<site>-<zone>`, no zone in cluster names), which PR #1 reversed.

**Labels** (§4). An InfraEnv lists every part of its name, and its site, as `spec.agentLabels`,
so its Agents carry them; NodePools select by those labels, never by node name:

| Object | Labels | Set by |
|---|---|---|
| InfraEnv → its Agents | `redbull.io/flavor`, `redbull.io/size` (`mtl` or `kv<cpu>`), `redbull.io/site`, `topology.kubernetes.io/zone` (plus assisted-service's own `infraenvs.agent-install.openshift.io: <name>`) | The InfraEnv's `agentLabels` |
| Agent | the above, and `redbull.io/claimed` | `claimed` at claim time (§5) |
| NodePool `agentLabelSelector` | `matchLabels` flavor, size, zone; `matchExpressions: redbull.io/claimed DoesNotExist` | The hostedclusters-setup chart (§6 item 3) |
| NodePool `nodeLabels` → tenant Node | `topology.kubernetes.io/zone` | The NodePool |
| KV hypervisor Node | `topology.kubernetes.io/zone` (**required**) | The KV NodePool's `nodeLabels`, in the day1 file |
| VirtualMachine | flavor, size, site, zone, `redbull.io/role` (`mce` or `worker`), `redbull.io/mce` | `create-vm` |

"c200 bare metal across all zones" is `flavor=c200, size=mtl`, not a name prefix (§4.a, the reason
column), which is why add-server-to-mce now draws by the InfraEnv's labels (workflows `29ef001`).
Adding the `claimed` expression changes a NodePool's template hash: confirm it is `InPlace` first.

---

## 5. The claimed-Agent mark and garbage collection

`naming-convention.md` §5, under AD23 ("Released Workers Are Destroyed or Wiped, Never Reused
As-Is"):

1. **Mark at claim time.** A Kyverno admission policy on each MCE labels an Agent
   `redbull.io/claimed=true` when its `spec.clusterDeploymentName` goes from empty to set. A label,
   because a selector reads only labels. herzi labels any bound Agent it finds unmarked, and alerts.
2. **Exclude everywhere.** Every NodePool carries `redbull.io/claimed DoesNotExist`. The provider
   reads the selector only when it picks a free Agent, so running nodes are unaffected.
3. **Collect.** herzi finds Agents labelled `claimed`, unbound (no `clusterDeploymentName`, no
   AgentMachine), not deleting and unchanged for a grace period, starts
   `remove-server-from-mce-<server>` for each (bounded parallelism), then a VM is destroyed and
   bare metal returns to server-scan for a reinstall. The id is the server, so a repeat, or
   `uninstall-server-from-hc`'s own child, is a 409.
4. **A marked free Agent is not spare**: herzi does not count it as claimable.
5. **Rollout:** label every bound Agent first, then turn the NodePool exclusion on.

It covers every way a machine leaves a cluster (scale-down, CAPI choosing another Machine, a
repair, `uninstall-server-from-hc`, a deleted cluster), so `update-nodepool` no longer releases
machines, and `claimed` replaces `redbull.io/uninstalling`. It contradicts AD26 ("only adds"),
which needs an amendment (§6 item 6). Owners still open: the chart (item 3), the Kyverno policy
(item 4), herzi's collection loop (item 5, proposed in herzi PR #1).

For Wingman: `DAY1_EXCLUDED_AGENT_LABELS` (ADR-0065) is rule 2 written per cluster file. **The key
is not settled:** the convention and herzi PR #1 (draft) say `redbull.io/claimed`; a plan on herzi's
branch `docs/retire-used-servers-plan` (`578edf1`, 2026-11-19, no PR, its decisions marked approved)
says `redbull.io/ever-installed`, and lets a NodePool carry that one `DoesNotExist` and nothing else.
herzi main (`0ef4d2a`) labels nothing and collects nothing. The order is the convention's either
way: the mark and the backfill before the exclusion.

---

## 6. The VM flow: create-vm and the KV agents

- **One install workflow for VM and bare metal** (AD29): herzi orders every pool through
  `add-server-to-mce` with a count. For a VM InfraEnv the run first runs `create-vm` as a child,
  then installs exactly that VM, with no server-scan draw (`inventory-controller.md` "Open"; P3
  criterion 4). The status diagram (11-22) marks this branch **not built**: "Bare metal done. Not
  yet: the create-vm child for VM pools (AD29)".
- **create-vm's design** is in `team-redbull/workflows`, `docs/design/create-vm-placement.md` on
  branch `docs/create-vm-placement` (`5e9441b`, 11-19), "authoritative"; the corrected plan is
  `KVW/docs/review/create-vm-plan-corrected.md`; workflows PR #26 (open, docs only: nothing is implemented "until the operator approves") carries it, "in review"
  (`components.json`). It names seeds `ocp4-<lifecycle>-seed-<site>-<id>` and InfraEnvs `<flavor>-kv<cpu>-<site>-<zone>`, the draft before the convention moved the zone and dropped the site. It replaces the deployed shape, whose two HTTP agents per KV cluster
  (`kv-capacity`, `kv-vm-api`) were never deployed, so "the deployed version cannot succeed".
  The design:
  - **The zone's KV clusters come from day1**: the hosted clusters of the site's seed folders,
    kept when their NodePools' `nodeLabels` name the zone, oldest first by the name's `id`
    letter, read by the cluster-lifecycle worker and cached per day1 commit.
  - **One placement at a time per zone** (AD32): a long-lived `KvZoneLockWorkflow`
    (`kv-zone-lock-<site>-<zone>`), a 5-minute lease, released once the VM object exists.
  - **First fit, oldest first** (AD33), with one buffer for every KV cluster,
    `HEADROOM_BUFFER_PERCENT` on the hub cluster-lifecycle worker, 15% by default (AD28, AD31).
  - **A `vm-lifecycle-worker` inside each KV cluster** (queue `vm-lifecycle-activity-<kv cluster>`)
    reads its cluster's figures and creates the VM: MAC from its `vmMacPrefix` plus 3 random
    bytes, name `ocp-<flavor>-kv<cpu>-<site>-<MAC>`, the §4.b labels plus `redfish-enabled` and
    `redbull.io/created-by`, memory = vCPU × 8 GiB, created Halted (kubevirt-redfish starts it).
  - **server-scan takes no part** in placement or creation (decision 2). `procedures/00-interfaces.md`
    §5.1 still calls VMs in server-scan "decided, not built"; server-scan has since built the
    collector: one `server-scan-collectors` release per KubeVirt cluster lists its VMs as servers
    of vendor `kubevirt`, `server_type: vm` (server-scan v5.0.0 and v6.3.0, its ADR-0058 to
    ADR-0060). A KV cluster's VMs are in server-scan only once that release runs for it, and a new
    VM only after the collector's next pass.
- **KV capacity** (AD27, AD28, AD30, `kv-capacity-controller.md`): a controller on each seed grows
  the zone's active KV cluster (oldest under 40 nodes) to keep 15% CPU free, through
  `update-nodepool`, and keeps one standby KV cluster (1 to 5 workers) through
  `provision-cluster`. It writes nothing itself and runs on the seed "rather than in Wingman".
  Specification only (`components.json`). `provision-cluster` waits for a human merge, so a
  standby KV cluster needs a person to merge it (open item O2).
- **The VM install is a bare-metal install afterwards:** kubevirt-redfish gives the VM a BMC, so
  the BareMetalHost, NMStateConfig, Agent and NodePool claim are the same (`00-interfaces.md` §5).

---

## 7. Decisions that constrain Wingman

| Decision | Source | What it means for Wingman |
|---|---|---|
| The capacity policy (`maxNodes` 40, `freeCpuPercent` 15, `standbyWorkers` 1-5, `standbyClusters` 1) is one file in the platform repo, **edited through Wingman by merge request**; Wingman never calls a controller | AD31; `kv-capacity-controller.md` §1.2, §3 | A new edit-by-MR page. The file's path and owner are open (O4) |
| The KV Capacity Controller runs on the seed, not in Wingman | AD27 | Wingman starts no KV growth and no standby cluster |
| Tenant workers are Agents on the Agent platform; VMs come from `kv<cpu>` InfraEnvs | C2, AD3 | A VM-backed cluster is a normal agent cluster file. The chart's `platform: kubevirt` (HyperShift's KubeVirt provider) is not the production model |
| `mce`, `seed`, `kv` are reserved flavors; names are refused when they break the rules | `naming-convention.md` §1; acceptance P7 | Wingman's create refuses them, and lists seeds and KV clusters as what they are |
| A tenant never sees zones, hubs, hardware mapping or inventory state | SC1.1; quality controls "Ease of Use" | Flavors carry node types per zone; Wingman picks the MCE (ADR-0050) |
| Machine-level objects are never in Git | AD22 | Unchanged: Wingman writes only cluster files |
| Released workers are destroyed or wiped; the controller collects claimed Agents | AD23; §5 | A free Agent labelled `claimed` is not free capacity |
| Workers upgrade in place, one node at a time, a zone at a time | AD24 | Unchanged (`upgradeType: InPlace` is the GitHub chart's default, `templates/nodepool.yaml`) |
| Workers may trail the control plane by two minors | AD25 | The upgrade workflow's rule, shown by Wingman |
| Wingman asks the orchestrator what a removal allows, draws the form from the answer, carries no version rule, and shows a refusal verbatim; choosing nodes needs control plane 4.19+ | Draft animation 20 (`docs/animations/_generate.py`, `20-remove-node-flow-draft`); acceptance M7, M8 | Proposed `GET /workflows/server-lifecycle/removal-options`, not built |
| A shrink is a lower count with the Machine marked first, never a deleted Machine | Procedure 19 | Unchanged: Wingman starts `update-nodepool` |
| A KV cluster's hypervisors leave only after their VMs are evacuated | Procedures 08, 09, 16 | Wingman must not scale down, delete or upgrade a KV cluster as if it were a tenant's |

---

## 8. Open items

From `naming-convention.md` §6: variant `x`; whether server-scan's availability query filters by
zone; **the hostedclusters-setup chart rendering `agentLabels`, the label selector and
`nodeLabels`**; the Kyverno claim policy; herzi's collection loop; the AD26 amendment; how Customer
MCE Nodes get their zone label; site names of at most 6 characters; `create-vm` building VM names
by the convention (it builds `ocp-<InfraEnv>-<6 hex>` today); `provision-cluster` or day1 CI
refusing a KV file without one zone; architecture §9.

From `kv-capacity-controller.md` §10: update-nodepool's id is `update-nodepool-<cluster>` (O1);
the human merge of a standby cluster (O2); one active/standby chain per server type or per zone
(O3); the policy file's path and owner (O4); `HEADROOM_BUFFER_PERCENT` not yet read from the
policy file (O5); `HighNodeUtilization` and `CompactAndScale` unconfirmed (O6).

From the create-vm plan's open points: memory fixed at vCPU × 8 GiB; a reused VLAN inherits a MAC
prefix; existing KV clusters need their ConfigMap; a lease expiring before the VM exists; Halted
VMs on no node; a down worker slowing the zone 30 seconds a run; the VMs' namespace (`inventory`
or `server-scan-vms`); **the day1 seed folders do not exist yet**.

From `review/mce-vm-placement-draft.md` §6 (D1-D6): dedicated management hosts or a management KV
cluster per zone; MCE VM anti-affinity and priority.

From the procedures: who picks the hub (03, answered for Wingman by ADR-0050); whether the merge
stays manual (03); a NodePool floor (19, D2); wiping bare metal (19, D5); cross-cluster live
migration for decommissioning (09).

**Inconsistencies found while reading** (to raise, not to fix here):
- Acceptance M4 and M5 scale "by node type" across zones; `update-nodepool` takes one NodePool by
  name since 2026-11-18 (ADR-0062), and procedure 19's D3 says a change by kind "is refused until
  the NodePools are evened out".
- Zones are soft (`assessment-brief.md` §4) or physical (the convention §2); and server-scan,
  named as the zone's source, has no zone yet.
- The used-Agent label: `redbull.io/claimed` (the convention, herzi PR #1) or
  `redbull.io/ever-installed` (herzi's `docs/retire-used-servers-plan`), §5.
- `components.json` (11-22) says update-nodepool is "on branch feat/update-nodepool, not merged";
  it is merged and in production (the ecosystem README's workflows table, 2026-11-23). It says
  Wingman's add-servers and upgrades are "off by default", and has "No tenant role yet".
- `inventory-controller.md` says herzi has never run against a real hub and every pool is in dry
  run; read herzi itself for its current state.

---

## 9. Files read

All of `docs/`: `architecture.md`, `naming-convention.md`, `inventory-controller.md`,
`kv-capacity-controller.md`, `vm-placement.md`, `GAPS.md`, `procedures/` 00 to 19 and their README,
`review/` (the assessment brief, the update-nodepool assessment, the corrected create-vm plan,
the MCE VM placement draft), `status/components.json`, `animations/README.md` and the steps of
`animations/_generate.py` for procedures 04, 19 and 20; `Acceptance Tests/acceptance-tests.md`;
`README.md`. Not read: the generated HTML, `deployment-view.png`, and the superseded
`workflow/` prototype beyond its file list.
