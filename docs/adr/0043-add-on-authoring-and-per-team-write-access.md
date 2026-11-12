# ADR-0043: Teams opt in to day2 writes per project; Wingman creates add-ons, edits team and fleet defaults, and a new fleet default takes over the clusters that already have the chart

Date: 2026-11-12
Status: Accepted; superseded in part by ADR-0053 (every write is confirmed against its preview's digest; a stale exclusion of an adopted cluster goes in the same commit; the review of 3.8.0)

## Context

The architect's vision, confirmed by the user on 2026-11-12: a team (dana,
redbull, ocp, ...) adds a new application to its repo from Wingman, chooses
its ArgoCD sync options there, and makes a new or existing application a
default across a fleet (every hosted cluster, every MCE, the hub, every UPI
cluster). And: "if the tenant didn't give Wingman create then this is off for
them. A tenant which trusts Wingman will give it create so it can do it."

Wingman has one GitLab account (`GITLAB_TOKEN`). Until now its docs said that
account must be Developer on every team project, and day2 offered every write
to every team.

What the platform templates (`apps/day2-service/tests/oracle/platform/`) say
about a chart becoming a fleet default:

- The per-destination `<team>-<cluster>-operators` ApplicationSet has two
  generators, the destination's own folder (`<clusterPath>/*`) and the
  defaults folder (`defaults/<scope>/*` minus exclusions). Its template names
  the wrapper app `<team>-<cluster>-<path.basename>` and uses nothing else of
  the path, so a chart folder in either place generates **the same wrapper
  app**, and through `deployApp.yaml` the same leaf
  `<team>-<cluster>-<chart>-deploy`. In both: the XOR rule's duplicate.
- The deploy-config stack (`operators.yaml`) and the workload-values stack
  (`deployApp.yaml`) list `defaults/<scope>/<chart>/` layers for **every** app
  of that chart on that kind of destination, whichever generator made it. So
  an excluded cluster that keeps its own folder still gets the default's
  values and deploy config below its own; an exclusion does not isolate it.
- Deleting a folder deletes the wrapper app; with `prune: false` and no
  resources finalizer the workload is orphaned (ADR-0022).

And deploy configs carry comments that matter (why a chart prunes, why it
uses a subchart): `defaults/mces/dhcp-api-token/dhcp-api-token.yaml` is
mostly comments.

## Decision

**Per-team opt-in.** `GitLabPort.access_level(project_id)` is the account's
role on a project: the higher of its project membership and its membership of
the project's group or any group above it (`GET /projects/:id` →
`permissions`). A team whose project gives Wingman **Developer or higher** is
writable; any other is read-only. day2 reads it per team, cached like the
team list (ADR-0011, answered stale while refreshed, ADR-0041), and every
day2 write (create, edit a default, make default, install, update, remove,
bulk install, and edit, approve and reject of its MRs) is refused first with
`403 TEAM_READ_ONLY`, its detail naming the team, the project and the role.
Reads are unaffected wherever the account can read. Teams, catalog entries
and fleet defaults carry `writable` and the reason, so the web shows the
state before anyone fills a form. Group membership is inherited by every
project below the group, so per-team opt-in means per-project membership.

**Sync options** are four settings, `auto_sync`, `prune`, `self_heal` and
`sync_options` (`domain.sync_policy`), read the way ArgoCD reads the leaf's
`syncPolicy`: `automated` present, even `{}`, is auto-sync (Wingman's
`auto_sync` used to read `{}` as manual; fixed). A team default gets the whole
policy; a fleet default only the `syncPolicy` keys that make the effective
settings what was asked over the team default, through Helm's merge (maps
merge, a list replaces, `automated: null` turns auto-sync off), checked by
merging. Other `syncPolicy` keys stay where they are. A new add-on starts from
the sync options most of the team's add-ons use, else manual sync with
`CreateNamespace=true` (leaves are manual-sync unless opted in, ADR-0022).

**Create** writes `operators/<chart>/<chart>.yaml` (lowercase `repourl`, and
`targetRevision`, `path`, `projectNamespace`, `syncPolicy`,
`ignoreDifferences` only when set) and `operators/<chart>/values.yaml`. The
name is a DNS label; a `repourl` on this GitLab must name a project Wingman
can read, and a revision must be one of its branches; a `repourl` elsewhere is
accepted with a warning. It may make the add-on a fleet default in the same
MR.

**Edits of a deploy config are in place** (`domain.yaml_text`): a key whose
value is unchanged keeps its lines byte for byte, a scalar keeps its line's
comment, a block mapping is edited key by key, any other changed value is
rewritten below the comment lines at its head, a removed key takes the
comment directly above it, a new key goes after its mapping's last key. The
result must parse to exactly the intended document and keep every other
comment line, else the edit is refused (`deploy-config-layout`). A miscased
`repoUrl` is renamed where it stands when a `repourl` is set. Values files
are replaced whole, as a cluster's values are today.

**Make default** writes `defaults/<scope>/<chart>/values.yaml` (always: it is
what makes the folder exist) and `<chart>.yaml` only for a sync override.
Every destination of that kind with the chart in its own folder is moved into
the default **in the same commit**: a non-empty `values.yaml` becomes
`defaults/<scope>/<chart>/values-<cluster>.yaml`, copied byte for byte; the
cluster's own `<chart>.yaml` is deleted; a `.gitkeep` keeps the cluster
registered if that was its last folder; a folder holding any other file
refuses the change (`adoption-blocked`). Because both folders generate the
same app names, ArgoCD keeps those Applications: nothing is deleted,
re-created or orphaned. The cluster's values move below its MCE-wide and
cluster-wide files, its deploy config goes, and the default's layers appear,
so Wingman merges each such cluster's deploy config and workload values
(chart defaults aside) before and after. A cluster where nothing changes
moves without asking; one where something changes (an emergency pin, a
namespace, sync options, a value) is listed key by key, and the request must
confirm exactly those clusters (`confirm_changes`, as ADR-0037 confirms
removals). On the hub the default is the hub's own folder, so nothing moves.
A default reaches the destinations the team's repo registers (ADR-0020).

**Fleet default edits** replace its `values.yaml` and edit its `<chart>.yaml`
sync override in place (`sync: null`: back to the team default's).

Every write runs the platform lints on the tree it would produce (ADR-0023),
takes `?dry_run=true` (every check, nothing opened), and is one MR:
`[Wingman/Day2] Create addon <team>/<chart> in the team catalog[ and as a fleet default on <scope>]`,
`... Update addon <team>/<chart> team default`,
`... Promote addon <team>/<chart> to a fleet default on <scope>` (the new
`Verb.PROMOTE`), `... Update addon <team>/<chart> fleet default on <scope>`;
labels and footer action `create-addon`, `update-default`, `make-default`
(ADR-0007). The web-visible API is in
`docs/notes/2026-11-12-day2-addon-authoring-api.md`.

## Alternatives rejected

- **A setting listing the writable teams.** Operators would keep a second
  list in step with GitLab; the membership is the real permission, and the
  team owns it.
- **Trying the write and mapping GitLab's 403.** It fails after the form is
  filled, and the web could not show the state in advance.
- **Refusing make default whenever a cluster has the chart in its own
  folder.** That is the common case, and the move is provably harmless when
  nothing changes.
- **Excluding those clusters instead of moving them.** The default's layers
  still apply to their apps (the stacks list them for every app), so values
  change anyway; and it needs a rewrite of `exclusions.yaml`, still deferred
  (ADR-0022).
- **Two MRs, remove then add.** A window with the app deleted and the
  workload orphaned, adopted again only when the second merges.
- **A YAML load and dump of deploy configs.** It drops the comments that
  explain them.

## Consequences

- Teams whose account membership is below Developer (or none) now show as
  read-only instead of failing at GitLab. An account that is Developer on the
  sigs group keeps every team writable; per-team opt-in needs the operators
  to move the account's membership to the projects that opt in
  (`docs/upgrade/3.7-to-3.8.md`).
- An instance-admin token with no membership reads as no access: Wingman's
  account must be a member, not an admin.
- A team that has just opted in shows as writable after the read cache's TTL;
  GitLab itself lets a new member see a private project a few seconds after
  adding it.
- Approving and merging still needs the merge right on the target branch,
  which a protected `main` may give only to Maintainers (unchanged).
- Left for later: **stopping being a default** (deleting the folder deletes
  the app on every destination it reaches, and `prune: false` orphans every
  workload: it must say so as loudly as remove does); authoring
  `ocp-versions/` pins; editing `ignoreDifferences` in the web.

## Verification

- `apps/day2-service/tests/oracle/test_render_chain_oracle.py`:
  `render_chain.py` renders the tree after Wingman's make-default MR with the
  same leaf apps, identities and workload values as before, and a created
  add-on with a default exactly as Wingman reports it.
- `tests/unit/application/test_authoring.py`: every write refused for a
  read-only team, the files and MRs of each action, adoption with and without
  changes, confirmation, refusals; `tests/api/test_authoring_api.py` the
  same over HTTP.
- `tests/unit/domain/test_sync_policy.py` (a hypothesis property: an override
  over any team default gives exactly the asked settings) and
  `tests/unit/domain/test_yaml_text.py` (comments kept, layouts refused).
- The GitLab contract (`wingman_core.testing.gitlab_contract`): project and
  group membership read back the same on the fake and on GitLab CE 19.5.3
  (ADR-0005).
