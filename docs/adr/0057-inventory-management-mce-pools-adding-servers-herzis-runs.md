# ADR-0057: Inventory Management: MCE pools, adding servers, herzi's runs

Date: 2026-11-13
Status: Accepted; amended 2026-11-13 (3.19.0: Install servers without live status); amended
2026-11-16 (3.38.0: Ready and Needs fix, a pool's total, collapsing an MCE, installing a
server with its health checks waived); amended 2026-11-23 (3.54.0: a pool's servers are named by
its InfraEnv's agentLabels); amended 2026-11-23 (3.55.0: herzi's used Agents apart, and the
NodePools that do not exclude its label); amended by ADR-0067 (2026-11-23: admins only, in the Infrastructure workspace);
amended 2026-11-24 (no Server Scan area: Inventory names servers as text, ADR-0066); amended
2026-11-24 (one MCE at a time: an MCE picker, several InfraEnvs picked and kept across MCEs, the
pools filtered; the runs stay every MCE's)

## Context

Servers reach a hosted cluster in two steps. The platform's
`add-server-to-mce` workflow makes a physical server an Agent in an MCE's
InfraEnv pool (the "inventory"); any NodePool on that InfraEnv that is short
of nodes then takes a free Agent, whatever cluster it belongs to. herzi, one
per MCE hub, starts the same workflow by itself to keep each pool topped up.

To see what is going on, a person opened server-scan (how many servers each
MCE holds), Temporal (what herzi and the runs are doing), and the
orchestrator (to add a server by hand). The user asked for one page in
Wingman for it: "a new one of Inventory which reflects the number of Agents
available in each MCE as the server scanner can provide, and then be able to
add another one by myself / see when herzi is making its own".

This is about the orchestrator's server workflows, not the fleet: the user
kept the cluster page as it is ("the cluster page is perfect"), and
server-scan's own UI is to come into Wingman later as a top-bar area of its
own.

## Decision

- **A Wingman sidebar page, Inventory Management, at `/inventory`, for the
  orchestrator's server workflows**: the available Agents per MCE and pool
  from server-scan, the add-server runs (herzi's and people's), and adding
  servers. **Everyone signed in reads it; only admins add** (the user,
  2026-11-13): the reads take `CurrentUser`, adding takes `AdminUser`, and a
  viewer sees no Add button (day1's 403 stays the guard). Not a top-bar
  area: those are for the big platforms. The API is
  `docs/notes/2026-11-13-inventory-management-api.md`.
- **It is not a fleet view.** A pool's servers are listed only with what a
  named install needs (name, hardware, lock, health). A server's full record
  belongs to the future Server Scan area, which Inventory will link to once
  it exists.
- **One view per thing.** The cluster page and MCE placement do not change.
  Inventory is the only view of MCE pools, and it reads server-scan through
  the existing `ServerInventory` port, adapter and cache (one cache entry for
  the Nodes tab, placement and Inventory): no second server-scan client.
- **The counts are server-scan's.** Per MCE: its servers, those in clusters,
  and the **available** Agents (`openshift_state` `INSTALLED_TO_INVENTORY`),
  with how many are usable by placement's rule. Each available server is put
  in the InfraEnv whose `ocp-<infraEnv>` starts its name (the workflow's own
  draw rule), from the MCE's InfraEnv list; and by hardware (vendor, model).
  A server matched to no InfraEnv is counted under none, not guessed. An MCE
  server-scan names nothing on is unknown, never zero.
- **Adding servers starts `add-server-to-mce`**, behind
  `DAY1_ADD_SERVERS` (off by default; needs `WORKFLOWS_API_URL`). Two ways:
  let the pool pick N (`count`, 1-20), or name servers (1-20) from the
  `AVAILABLE` servers named `ocp-<infraEnv>…`. Day1 checks only that the MCE,
  the InfraEnv and each named server are ones the page showed, then starts
  the run, logs who, and shows the orchestrator's answer per run. The dialog
  says that the server joins the MCE's pool for that InfraEnv, not one
  cluster; that each server is its own run; and that sending again installs
  more. A start is never retried (ADR-0006); an unanswered one is
  `AMBIGUOUS_WRITE`: look at the runs first.
- **Locks.** server-scan's lock is its `reservation` (held by the add-server
  or uninstall workflow, or set by a person through its admin API; herzi
  never touches it). The workflow fails a named run on a locked server, one
  in maintenance, or a contested one. Wingman shows each such server with
  why, and does not offer it for a named install; the workflow stays the
  judge of everything else (health is shown, not refused).
- **The runs, herzi's included.** The orchestrator's add-server runs, the
  newest first, with MCE, InfraEnv, slot or server from the run id, and the
  workflow's own phase, server and error. A named run is a person's (herzi
  only sends `count`); a pool draw is "herzi or a person": the orchestrator
  records no `requested_by`, so Wingman never guesses.
- **herzi's own marks are left out of the alpha.** Its InfraEnv annotations
  (`blocked-until`, `state`) need a new MCE read and grant; its numbers and
  decisions live in its metrics and logs. Both are named as missing. (Since
  3.55.0 the marks are shown, from the InfraEnv list already read: the
  3.55.0 amendment.)
- **Metrics**: the `workflows` operation `start_add_server`; the runs reuse
  `list_runs` and `get_run` (ADR-0010).
- **The fake fleet** (`DAY1_FAKE_FLEET`, development) fakes the runs: they
  walk sample phases, take a server, and leave it in the MCE's inventory; a
  fake herzi starts a pool draw now and then on one short pool.

## Alternatives rejected

- **A fleet table on this page** (every server, its record, filters). That is
  server-scan's, and comes with its own area later; two fleet views would
  drift.
- **Add servers from the Nodes tab.** The user keeps the cluster page as it
  is, and a server joins an MCE's pool, not a cluster: the pool's page is the
  honest place.
- **Count free Agents from the MCE.** The user asked for server-scan's
  count; the MCE's Agents per InfraEnv stay placement's (ADR-0050), which
  needs them for one create.
- **Offer every server for a named install and let the run fail.** A locked
  or maintenance server fails for certain: showing why is cheaper than a
  failed run.
- **Tell herzi's runs from a person's by timing or slot.** A guess; the
  orchestrator would need `requested_by` (asked of the team).

## Consequences

- Admins add servers without opening the orchestrator; everyone sees
  herzi's runs beside people's.
- A pool draw sent twice installs twice: the dialog says so, and nothing
  retries.
- On a pool herzi manages, a named install is outside herzi's accounting
  until its Agent appears, so herzi may order more meanwhile (it never
  shrinks a pool). Asked of the team.
- The page needs `SERVER_SCAN_URL`; the runs and adding need the
  orchestrator; adding needs live status for the InfraEnv list.

## Verification

- `tests/unit/domain/test_inventory.py` and `test_add_server.py`: counting,
  matching, a pool's servers and their refusals, run ids and origin.
- `tests/unit/infrastructure/test_add_server_workflow.py`: the start's
  answers (202, 409, 422, 502, 504, not sent), the run list and one run, on a
  mocked transport; `test_fake_add_server.py`: the fake's walk and herzi.
- `tests/api/test_inventory_api.py`: the routes, everyone reads and only
  admins add, off and
  unconfigured, start 202/409/422/502/504, and a locked server refused for a
  named install.
- `apps/web/e2e/tests/inventory.spec.ts`: the page, the runs and the dialog
  on mocked routes; `apps/web/lib/inventory/inventory.test.ts` (Vitest): the
  grouping, the run labels, what the dialog may send.
- 2026-11-13: the stack with `DAY1_FAKE_FLEET=true DAY1_ADD_SERVERS=true`
  shows the counts, herzi's fake runs, and an install by count and by name.

## Amendment (2026-11-13, 3.19.0): Install servers from the page, without live status

The user could not find installing on the page ("there is no Install Server
(that we took from the workflow orchestrator)"). On the team's sandbox,
adding was off, and even on it needed live status for the MCE's InfraEnv
list, which is off there: the only entry was a small Add on a pool row, and
without the list there were no pool rows.

- **A page-level "Install servers"** in the header, the orchestrator's own
  wording, opening one dialog: pick the MCE (day1's MCEs by site) and the
  pool, then "Let the pool pick" N or "Choose servers", with the three
  sentences, the lock rules and the never-retried submit as before. Each
  pool row keeps a shortcut, now **Install**, that opens the same dialog on
  that MCE and pool.
- **The pool is picked or typed.** The choices are the InfraEnvs the page
  knows on that MCE: its pools, and those its pool-draw runs filled. An
  admin may type another name; the dialog only checks it is a DNS label,
  and so does day1 (`422`).
- **Day1 no longer reads the MCE to install.** It checks the MCE is a day1
  MCE and the InfraEnv a DNS label; whether the MCE has that InfraEnv is the
  workflow's first phase (`validating-infraenv`), a FAILED run naming it
  otherwise. This is what the orchestrator's own form does (its InfraEnv and
  MCE are typed text): Wingman keeps no second copy of the check, and an
  install works with live status off. A pool's servers (§2 of the API note)
  are read from server-scan alone too.
- **Without the MCE's own list**, the pools are the InfraEnvs the MCE's day1
  cluster files name (`nodepool[].infraEnvName`), marked
  `infra_envs_from: "day1"`, and the card says so in a quiet line with the
  reason in a tooltip. When the MCE's list is read it is the only source.
- **Off, it says why.** With `DAY1_ADD_SERVERS` off or no orchestrator, an
  admin sees Install servers disabled with day1's one-line reason in a
  tooltip ("Installing servers is off on this Wingman"), instead of nothing;
  a viewer sees no button. Live status is no longer a reason.

Rejected: keeping the InfraEnv check against the MCE when live status is on
(two behaviours, and the workflow checks it anyway); reading InfraEnvs from
server-scan's server names (an InfraEnv is not a prefix one can cut off a
name: `ocp-dell-r660-site1-128c-1024gb-<serial>` is not in pool
`dell-r660-site1-128c-1024gb-5tb`); herzi's InfraEnv annotations, still left
out (a new MCE read and grant, and the hub client is at its size ceiling).

Consequence: a typed InfraEnv the MCE lacks is a FAILED run in the runs
table, in the workflow's words, not a refusal before the start.

Verification: `apps/day1-service/tests/api/test_inventory_install_api.py`
(the page and installs with no hub, a typed InfraEnv, a non-label `422`, an
unknown MCE `404`, a failing hub falling back to the day1 files);
`apps/web/lib/inventory/install.test.ts` (Vitest: the label rule, the known
InfraEnvs, the pickers); `apps/web/e2e/tests/inventory.spec.ts` (the header
button, a picked and a typed pool, the row's preselected dialog, the
disabled button and its tooltip, a viewer's page with no button).

## Amendment (2026-11-16, 3.38.0): Ready and Needs fix, a pool's total, collapsing an MCE, installing a server with its health checks waived

The user (2026-11-16): each MCE should collapse so the others can be seen;
a pool's "free" count should say what can be installed today and what needs
fixing first; a pool should say what it could reach in all; and an admin
should be able to install a server that fails a health check, after
confirming. The platform's `add-server-to-mce` has that last one already, as
a hidden `allow_unhealthy` (team-redbull/workflows, CLAUDE.md §4,
`AddServerToMceInput`): install the **named** server although its own
condition fails a health check, never past a safety refusal, and refused
(422, `AllowUnhealthyNeedsServerNameError` inside a run) on a pool draw.

- **Ready and Needs fix replace Free.** A pool's free servers are the
  `AVAILABLE` ones named `ocp-<infraEnv>…`. Those Wingman offers (no safety
  refusal: unlocked, out of maintenance, not contested) are split by
  server-scan's row with the rule the workflow's pool draw asks server-scan
  for (`/servers/available?health=HEALTHY`: unclaimed, healthy, reachable,
  unreserved, out of maintenance):
  - **Ready**: `HEALTHY` and reachable, what a pool draw could pick today;
  - **Needs fix**: server-scan's health is anything else (`WARNING`,
    `MAJOR`, `CRITICAL`, `UNKNOWN`) or it cannot reach the BMC, each with
    why (`health CRITICAL`, `BMC unreachable`). A pool draw never picks one.

  Locked, in-maintenance and contested servers are neither: those are the
  workflow's safety refusals, which nothing waives. They stay listed with
  why, as before. One rule, `domain/inventory.py`'s `health_problems`; the
  existing `drawable` is that rule now, which also leaves a contested server
  out of Ready (the workflow refuses it).
- **How close that is to the workflow.** Wingman reads only the row
  (overall health, reachability). The workflow also judges what the row
  does not carry: server-scan's network category and its live recheck of
  each candidate, two link-up NICs on distinct ports at bond selection, a
  known BMC vendor and address. So a Ready server's run may still be
  refused, and the column's tooltip says so; a Needs fix server is one a
  pool draw certainly skips. Wingman keeps no copy of those checks: they
  stay the workflow's (Wingman starts runs and shows them).
- **Total** = Available + Ready + Needs fix: what the pool reaches once
  every free server is fixed and installed. Per pool, and on each MCE's
  card, where a free server named for two of its pools is counted once.
  Locked, in-maintenance and contested servers are not counted; a free
  server named for pools on two MCEs counts on both, as it is in neither
  yet. The "No InfraEnv" row's total is its available. Explanations are in
  the tooltips.
- **Each MCE collapses.** The card's title is a disclosure button
  (`aria-expanded`, `aria-controls`, Enter and Space); collapsed, the card
  keeps its counts line and hides its pools. Expanded by default. The
  collapsed MCEs are a per-viewer convenience in `localStorage`
  (`wingman-inventory-collapsed`), read and written in `try`/`catch`:
  with storage blocked the choice lasts for the page.
  *(Superseded 2026-11-24: the page shows one MCE at a time, picked, so
  nothing collapses; see that amendment. `wingman-inventory-collapsed` is
  no longer read.)*
- **Installing a server that needs a fix**, after a confirmation. In the
  dialog's "Choose servers", a Needs fix server can be checked (a locked,
  in-maintenance or contested one still cannot). Install then opens a
  confirmation step that lists each such server with what server-scan
  shows wrong, says that the workflow's health checks are waived for every
  server of the request (its health tier, its network, the BMC's
  reachability, the live recheck, a bond member whose link is down), and
  that its safety refusals still apply (claimed, contested, in maintenance,
  another run's lock, an InfraEnv the MCE lacks). Only "Install with checks
  waived" sends `{"server_names": [...], "allow_unhealthy": true}`; Back and
  Cancel send nothing. A pool draw never sends it, and day1 refuses
  `allow_unhealthy` without `server_names` (`422 VALIDATION_ERROR`) before
  calling the workflow, as the orchestrator does. Admins only, as every
  install; the start is logged `servers_add_started` with
  `allow_unhealthy=true`, at warning, "with health checks waived". Metrics:
  the same `start_add_server` operation and outcomes (ADR-0010), no label.
- **The runs say what was waived.** A run's `allowed_unhealthy` (its
  progress's, else its result's) is the run's `health_checks_waived`, each
  `check: observed`, shown in the runs table as "checks waived" with the
  list in a tooltip. There is no MR and no other record of an install.
- **The fake fleet** fails a named install of a server that needs a fix
  unless the start asked for `allow_unhealthy`, then records the waived
  checks on the run, as the workflow does. Its fixture has a CRITICAL,
  unreachable server in `dell-r650-site1-96c-768gb`.

The workflow keeps `allow_unhealthy` out of its OpenAPI, its docs and every
UI on purpose (the operator's "easter egg", 2026-10-31, after an incident
that had to install servers with one NIC up and no RAID). Wingman shows it
at the user's request, to admins only, behind a step that names what is
waived; to tell the team.

Rejected:

- **Locked or in-maintenance servers as Needs fix.** Neither is the
  server's health: maintenance is a person's "do not touch", a lock a run in
  flight, and the waiver passes neither.
- **Reading each server's full record** for its health categories and
  reasons: a read per server, for what the row's tier and reachability
  already decide (the draw filters on them); the server's page in the
  Server Scan area has the rest.
- **Splitting a mixed choice into two starts** (the Ready servers without
  the waiver, the others with it): two writes from one click, the second
  lost if the first is unanswered. One request; the confirmation says the
  waiver covers every server named in it.
- **A stricter day1 rule** (every named server must need a fix): a second
  rule beside the workflow's, which takes the waiver with any named server.
  The dialog sends it only after a Needs fix server is confirmed.
- **Offering the waiver for a Ready server** the workflow then refuses on a
  check Wingman cannot see: Wingman could not say what would be waived. Its
  FAILED run says why, in the workflow's words.

Consequences: a pool says what an install takes today and what waits for a
repair; a server installed with its checks waived may join a NodePool with
one NIC up or a RAID fault, which the confirmation says and the run
records; Ready stays server-scan's view, so a run may still fail.

Verification: `tests/unit/domain/test_inventory_ready.py` (the split, the
totals, the order); `tests/api/test_inventory_waiver_api.py` (the counts,
the candidates' groups and reasons, the `422` before the workflow, the
payload, the fake's refusal and its record, the log);
`tests/unit/infrastructure/test_add_server_workflow.py` (the body, the
run's waived checks); `apps/web/lib/inventory/waiver.test.ts` and
`collapsed.test.ts` (Vitest; removed 2026-11-24 with the collapse);
`apps/web/e2e/tests/inventory-ready.spec.ts` (collapsing and its memory,
until 2026-11-24; the counts and totals, the list's groups, a pool
draw never sending the waiver, the confirmation, Back sending nothing, the
`422`).


## Amendment (2026-11-23, 3.54.0): a pool's servers are named by its InfraEnv's agentLabels

The platform's naming convention left draft on 2026-11-22 (its single
source: Idan-Maimon/kubevirt-workflows `docs/naming-convention.md`). An
InfraEnv is `<flavor>-<mtl|kv<cpu>>-<zone>` and lists its flavor, its size
and its MCE's site as `spec.agentLabels` (`redbull.io/flavor`,
`redbull.io/size`, `redbull.io/site`, with `topology.kubernetes.io/zone`);
a server is `ocp-<flavor>-<mtl|kv<cpu>>-<site>-<serial|mac>`. The zone is in
no server's name. add-server-to-mce follows it on main (team-redbull/workflows
`6fdfe5d`, `29ef001`): its pool draw asks server-scan for
`^ocp-<flavor>-<size>-<site>-` from those three labels, fails the run
(`InfraEnvAgentLabelsError`, nothing allocated) when one is missing or not
one lowercase word, and filters by no zone. A named install is not matched
to the pool at all. Matching servers by `ocp-<infraEnv>`, as above, listed
no candidate under the new names, and day1 refused a named install the
workflow takes. The user approved the direction (2026-11-23).

- **The labels name a pool's servers** (`domain/infra_env_pools.py`: the
  workflow's `_POOL_LABELS`, `agent_label_problems` and
  `pool_prefix_from_labels`, in Wingman's terms). `HubApi.infra_envs` now
  returns each InfraEnv with its `spec.agentLabels`, from the same list call
  and cache (`MCE_INFRAENV_CACHE_SECONDS`): no new read, no new grant. A
  pool's `server_prefix` is `ocp-<flavor>-<size>-<site>-`, case as given;
  `label_problems` says, in the workflow's words, why it has none.
- **No zone.** The workflow does not filter by zone and server-scan
  (v6.9.2) records none, so neither does Wingman: the InfraEnvs of one
  flavor and size in several zones of a site draw from the same servers,
  and each counts them as ready (the MCE's card counts each once).
- **An available Agent's pool.** server-scan does not say which InfraEnv
  an Agent is in. A server is in the one pool whose prefix names it; when
  several do (the zones above), or none, a held lock on the MCE says which;
  otherwise it is counted under none, now labelled "No single InfraEnv",
  never guessed. A server named before the convention fits no prefix.
- **Without the labels** (live status off, the hub unreadable, an InfraEnv
  the MCE does not list) a pool's servers' names are unknown: it counts no
  ready or needing a fix (a dash, with why), and its list is every free
  server, said so above the list. The workflow checks the server named.
- **An InfraEnv that lacks a label** is marked on its row, and the install
  dialog says, before a pool draw, that the workflow would refuse it.
  Wingman still sends it: day1 keeps no MCE read before an install (the
  3.19.0 amendment), and a worker predating the labels draws by the
  InfraEnv's name.
- **A named install** is checked only for the safety refusals (no such
  server, not `AVAILABLE`, locked, in maintenance, contested): day1 no
  longer refuses a server whose name another pool's labels give, since the
  workflow takes it.
- **The fake fleet** follows the convention: `dev/fleet-fixtures/mce.yaml`
  gives site1-a's new InfraEnvs (`r760-mtl-az1`, `r760-mtl-az2`,
  `r650-mtl-az1`, `g12-mtl-az1`) their labels, and site1-b's `r650-mtl-az2`
  labels without its site; Inventory's demo servers are named
  `ocp-<flavor>-mtl-site1-<serial>`, lowercase; the fake herzi fills
  `r760-mtl-az1`; the fake workflow draws by the labels and fails a draw
  into an InfraEnv without them, as the workflow does. The fixture
  clusters' older InfraEnvs have no labels.

Rejected:

- **Filtering by zone.** Nothing deployed does: the workflow's draw has no
  zone, and server-scan exposes none (the convention's open item 2).
- **Keeping `ocp-<infraEnv>` beside the labels**, for InfraEnvs made
  before the convention: a second rule the deployed workflow no longer
  uses.
- **Reading the MCE's Agents** to place an available Agent in its InfraEnv
  (their `infraenvs.agent-install.openshift.io` label): a new read per MCE
  on every page load, while the counts stay server-scan's (above). Left to
  the user.
- **Refusing a pool draw into an InfraEnv that lacks a label.** The
  workflow is the judge, and a worker predating the labels still draws by
  the name.

Consequences: under the convention a pool lists and counts the servers the
workflow draws; an InfraEnv without its labels says so before a pool draw
fails; with live status off a named install picks from every free server. A
site whose name has a dash (`bat-yam`) is not a label value the workflow's
pool draw accepts.

Verification: `tests/unit/domain/test_infra_env_pools.py` (the prefix, the
workflow's words, an unread pool); `test_inventory.py` and
`test_inventory_ready.py` (one pool, two zones, a lock, unread pools, every
free server, a named server of another pool);
`tests/unit/infrastructure/test_hub_api.py` (agentLabels read) and
`test_fake_add_server.py` (a draw by the labels, refused without them, a
named install without labels); `tests/api/test_inventory_api.py`,
`test_inventory_install_api.py`, `test_inventory_waiver_api.py`;
`apps/web/lib/inventory/inventory.test.ts` (Vitest) and
`apps/web/e2e/tests/inventory-names.spec.ts`.


## Amendment (2026-11-23, 3.55.0): herzi's used Agents apart, the NodePools that do not exclude its label, and herzi's marks

herzi's plan to retire used servers (team-redbull/herzi, branch
`docs/retire-used-servers-plan`, `578edf1`, its decisions approved; not on
herzi's `main`, `0ef4d2a`, which labels nothing): herzi labels every Agent
bound to a cluster `redbull.io/ever-installed` as it binds, and once such an
Agent is free again (a scale-down, an uninstall, a deleted NodePool or
cluster, a Replace rollout) it is *retiring*: never spare, and removed from
the MCE through `remove-server-from-mce`. server-scan writes it as
`INSTALLED_TO_INVENTORY`, like any free Agent, so the page counted it as
available. herzi holds such an Agent's removal while any Agent NodePool
whose selector matches it lacks the exclusion (its rule 6), and every
NodePool takes the exclusion through its own cluster's merge request
(ADR-0065). The user asked for Wingman to follow what herzi has built and
planned (2026-11-23).

- **Used Agents are read from the MCE**, only them: one label-selected list
  per used-Agent key, `<key>,!agentMachineRef` (`HubApi.used_agents`), in
  `MCE_INFRAENV_NAMESPACE` or the whole hub, kept 30 seconds (the page's
  refresh). The keys are placement's (ADR-0050's 2026-11-23 amendment,
  `WorkflowKeys.used_agent_labels`): `DAY1_EXCLUDED_AGENT_LABELS` when set,
  else herzi's label. The existing grant (`list` on `agents`, the 3.4
  ClusterRole) covers it; no new Secret or value. A hub answers with the
  few labelled free Agents, not its inventory, so this reverses the 3.54.0
  amendment's rejection of reading the MCE's Agents on every page load for
  these Agents only. Without live status they are not read (`used: null`);
  a read that fails says why on the card (`used_error`).
- **Apart, never available.** A used Agent bound to nothing is joined to its
  server-scan row as the nodes view joins an Agent (BareMetalHost name, MAC,
  serial); that row leaves the available ones, and the used Agent is counted
  in its InfraEnv label's pool, its servers by name (`pools[].used`), and on
  the MCE (`used`). Neither counts in a total. One server-scan has no row
  for still counts, by its BareMetalHost's name. On the page: "2 used", in
  the warning colour, beside the MCE's available and in the pool's
  Available cell, its tooltip naming the servers and why ("waiting for
  herzi to remove").
- **The NodePools that do not exclude the label**, from the MCE's cluster
  files (`domain/used_agents.unguarded`; no new read): each agent nodepool
  whose `excludeAgentLabels` lacks a key, by the NodePool name the MCE
  shows, with its InfraEnvs and whether it is `upgradeType: Replace` (the
  cluster's merge request leaves those out). KubeVirt clusters take no
  Agents. `GET /api/day1/inventory` lists them per MCE (`unguarded`); the
  page shows them once they matter, when herzi has used Agents on the MCE or
  the deployment excludes the label: "3 NodePools in 2 clusters do not
  exclude redbull.io/ever-installed", which opens to each cluster, linked to
  its page, and its NodePools. The tooltip says herzi removes no used Agent
  until each excludes it, and that each cluster takes it through its own
  merge request.
- `GET /api/day1/inventory` gains `used_labels` (`keys`, and `source`:
  `setting` or `herzi`).
- **herzi's marks on a pool's InfraEnv** (herzi's `main`), read from the
  InfraEnv list Wingman already lists, its `metadata` this time
  (`domain/herzi_marks.py`; no new read or grant, unlike what the decision
  above assumed): `herzi.redbull.io/ignore` (the label, herzi's default
  `ignoreLabel`: herzi does not read the pool), `herzi.redbull.io/paused:
  "true"` (herzi orders nothing, and by its plan removes nothing),
  `herzi.redbull.io/blocked-until` (an order in flight or unclear) and
  `herzi.redbull.io/state`'s `capFailAt` newer than its `lastOKAt` (its last
  order found no hardware). Each pool carries them (`pools[].herzi`); the
  row shows a quiet badge, the first that applies ("herzi paused"), its
  tooltip saying each, and a paused pool's used count says herzi removes
  none of them until it is resumed. A deadline that has passed is not shown.
  Malformed marks are none. herzi's config (an excluded or paused pool, dry
  run) and its metrics stay out of reach.

Rejected:

- **Reading every Agent of the MCE** and filtering by label: the inventory
  of every MCE on every refresh, for the few that are used.
- **herzi's own numbers** (`herzi_pool_retiring`, `herzi_retiring_agents`):
  planned metrics on herzi's Prometheus endpoint, which Wingman reads
  nowhere; keep extras thin.
- **Listing herzi's `remove-server-from-mce` runs** beside the add-server
  runs: the run id carries no MCE and is also started by add-server-to-mce's
  rollback and older uninstalls (herzi's plan, §3.1), so a run could not be
  told to be herzi's; and herzi's remover is not built.
- **A button that opens each cluster's merge request** from this page: the
  per-cluster merge request has its API (ADR-0065) and is the cluster's,
  not the inventory's; the list links each cluster.

Consequences: until herzi labels Agents nothing changes on the page; once
it does, a pool's available count leaves out servers that herzi is about to
remove, and the clusters still to give the exclusion are one click from
their pages. An `InPlace` NodePool that gains the exclusion touches no
running node; a `Replace` one would replace every node, and is listed for a
person to change first.

Verification: `tests/unit/domain/test_inventory_used.py` (the join, apart
from available and the totals, a pool no InfraEnv lists, not read);
`tests/unit/domain/test_used_agents.py` (retiring, the unguarded
nodepools); `tests/unit/infrastructure/test_hub_used_agents.py` (the
selector per key, namespace, paging, each Agent once, a bad key never sent,
the fake, the cache); `tests/unit/domain/test_herzi_marks.py` (each mark,
Go's times, a recovered or malformed state, the adapter's parse);
`tests/api/test_used_agents_api.py` (the overview with herzi's label and
with the setting's, the unguarded nodepools, no live status, a pool's
marks); `apps/web/lib/inventory/used.test.ts` and `herzi.test.ts` (Vitest)
and `apps/web/e2e/tests/inventory-used.spec.ts`.

## Amendment (2026-11-23, by ADR-0067): admins only

The user (2026-11-23): "In addition to inventory management — Herzi keep the
place of the customers and filling their request." herzi fills the
customers' demand, so customers do not manage inventory, and the pools name
the MCEs, which a viewer never knows of.

- **Every read is an admin's** (`AdminUser`): `GET /api/day1/inventory`,
  `/inventory/runs` and a pool's `/candidates` answer a viewer `403
  FORBIDDEN`, before server-scan or the orchestrator is asked. "Everyone
  signed in reads it" above no longer holds; adding was an admin's already.
- **The page moves to the Infrastructure workspace** (ADR-0067), with the
  MCEs and seeds; a viewer has no entry for it, and `/inventory` shows a
  viewer what any admins-only page does.
- A seed is a card like any MCE: herzi fills its pools too.

Verification: `apps/day1-service/tests/api/test_inventory_api.py`
(`test_only_admins_read_and_add`).

## Amendment (2026-11-24): no Server Scan area; Inventory names servers as text

"The future Server Scan area" and "the server's page in the Server Scan area"
above were written while that area was planned. It was built (ADR-0048) and
removed in 3.52.1 (ADR-0066): the team keeps server-scan apart from Wingman.

- **Inventory names a server as text**, in a pool's servers and in the runs:
  no link to a page of its own, and the runs carry no `server_id` for one
  (ADR-0066). A server's full record is server-scan's own UI, which the
  Infrastructure sidebar links to (ADR-0067).
- Nothing else here changes: Inventory still reads server-scan through the one
  `ServerInventory` port, adapter and cache.

Verification: `apps/day1-service/tests/api/test_inventory_api.py`
(`test_runs_are_listed_from_the_orchestrator_alone`: a run names its server
and carries no `server_id`) and `apps/web/e2e/tests/platforms-apart.spec.ts`
(nothing in Wingman leads to a page of its own for server-scan).

## Amendment (2026-11-24): one MCE at a time; the InfraEnvs picked across MCEs; the runs stay every MCE's

The user (2026-11-24): "I think this is better to make a MCE Selector +
InfraEnv because I will get some of 60 InfraEnv maybe. About the herzi down
there keep it for all the MCEs all of the infraenv. It's important." Then:
"and we can select multiple infra envs! And changing mce not have to change
the infraenvs!" One card per MCE, each with a row per InfraEnv, stopped
fitting a page once an MCE holds about 60 pools. Web only: day1's API, and
what it counts, do not change.

- **One MCE at a time, picked.** A searchable picker at the top lists day1's
  MCEs by site, in day1's order, each with its available Agents; one
  server-scan names nothing on (the old "Not in server-scan: …" line) is
  still offered, marked "not in server-scan", and shows "No pools on this
  MCE" when its hub names none either. Below it, the MCE shown has what its
  card had: its counts, the line saying its pools come from its cluster
  files, its used Agents unread, the NodePools that do not exclude the
  used-Agent label, then its pool table. A seed is an MCE in the picker like
  any other. The default is the first MCE, in day1's order, that server-scan
  knows or whose hub names pools.
- **The InfraEnvs picked, several at once, by name.** A second picker beside
  the table's filters lists the MCE's InfraEnvs with a search, each a
  checkbox, and "Pick the n found" for a search's results; none picked shows
  every pool. The picked names are listed under it, each removable, and
  "Unpick all" empties them. They are **names, not one MCE's**: the
  platform's InfraEnv is `<flavor>-<mtl|kv<cpu>>-<zone>`, with no hub and no
  site, so every hub at a site has the same pool names. A change of MCE
  keeps them; the new MCE shows those it has, and says quietly which it
  lacks ("Not on <mce>, kept for the other MCEs"), still picked, so going
  back shows them again. An MCE with none of them says so, with Clear
  filters.
- **In the URL, and remembered.** `?mce=<name>&infraEnv=<a>,<b>` (also
  repeated `infraEnv`): a link opens one MCE (each Customer MCE and the
  Overview's Free Servers rows link to theirs, through one helper,
  `inventoryHref` in `lib/inventory/view.ts`), and a reload keeps the view. Each change replaces the history entry, as the
  clusters list's filters do. Both parts are also kept per viewer in
  `localStorage` (`wingman-inventory-view`, `{mce, infraEnvs}`), read and
  written in `try`/`catch`; the URL's part wins, else the remembered one,
  each on its own, so a link to one MCE keeps the viewer's InfraEnvs. An
  unknown `?mce=` shows the default MCE and says so in one quiet line. No
  name is trusted to exist: an MCE or InfraEnv day1 does not list only
  narrows the view.
- **The table's own filters**, not remembered: a search on part of the name;
  Zone and Size, one each or All, from the names that follow the convention
  (none shown when no name does; a name before it, such as
  `dell-r660-site1-128c-1024gb-5tb`, is found by the search only); and "Only
  with servers" (available, ready, needs fix, or herzi's used Agents). They
  combine with the InfraEnvs picked and stay while the MCE changes, a zone
  or size the new MCE lacks being dropped. "n of m InfraEnvs" says what
  shows; when nothing does, "No InfraEnvs match" offers Clear filters, which
  clears them and the InfraEnvs picked. The servers no one InfraEnv names
  show, last, only while nothing filters by name.
- **A long table stays readable.** It scrolls inside its own frame (at most
  70% of the window) under a sticky, translucent header, the runs table's
  look; a phone's page keeps its width and the table scrolls sideways
  inside. InfraEnv and Available sort the rows (by name, natural order, the
  default; by available, most first), the header saying which
  (`aria-sort`).
- **The runs stay every MCE's.** The Runs section lists every MCE's and
  every InfraEnv's add-server runs, herzi's and people's, whatever is picked
  above, and says so beside its title ("every MCE and InfraEnv"). The
  header's total available stays the whole fleet's ("across n MCEs").
- **Install servers** in the header opens the dialog on the MCE shown; a
  row's Install still opens it on that MCE and pool.
- **Nothing collapses any more** (the 3.38.0 amendment's collapse is
  superseded): its code and `wingman-inventory-collapsed` are gone.

Rejected:

- **Keeping the stacked cards with a filter over them**: 60 rows per MCE
  times the MCEs is still one long page, and herzi's runs fall far below.
- **The InfraEnvs picked per MCE**: the names carry no hub, and the user
  wants them to survive a change of MCE.
- **Filtering the runs by the picks**: the user wants herzi's and people's
  runs on every MCE and InfraEnv in view, whatever is picked.
- **Zone and size as picks** (selecting every matching InfraEnv): two ways
  to pick the same names, and an `az1` and `mtl` pick would add, not narrow.
  They are filters; the search's "Pick the n found" picks by a part of the
  name.

Verification: `apps/web/lib/inventory/pool-filter.test.ts` (a name's flavor,
size and zone, the zones and sizes offered, the picks split by MCE, the
filters combined, the order) and `view.test.ts` (the URL both ways, storage
blocked or malformed, which MCE and InfraEnvs show) (Vitest);
`apps/web/e2e/tests/inventory-picker.spec.ts` (picking an MCE, `?mce=` and
an unknown one, the header's Install servers, several InfraEnvs picked and
kept across MCEs with those an MCE lacks reported, the filters, the empty
state, the order and the sticky header, the runs never filtered, a phone's
width), with `inventory.spec.ts`, `inventory-names.spec.ts` and
`inventory-used.spec.ts` showing the other MCE by the picker or `?mce=`.
