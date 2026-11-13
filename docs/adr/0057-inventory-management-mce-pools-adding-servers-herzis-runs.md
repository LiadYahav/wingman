# ADR-0057: Inventory Management: MCE pools, adding servers, herzi's runs

Date: 2026-11-13
Status: Accepted; amended 2026-11-13 (3.19.0: Install servers without live status)

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
  decisions live in its metrics and logs. Both are named as missing.
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
