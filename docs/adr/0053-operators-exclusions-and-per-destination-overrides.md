# ADR-0053: A team's operators get their own pages; Wingman edits `exclusions.yaml` in place, overrides one destination's values or deploy config, and every authoring write is confirmed against its preview

Date: 2026-11-12
Status: Accepted; amended 2026-11-12 (the Operators pages are folded into Addons: one place, called add-ons) and 2026-11-13 (no exclusions in Wingman; a subset of MCEs is per-MCE installs; hosted-cluster specifics belong to flavors and create)

## Context

The user, on 2026-11-12: "Creating a new operator under operators/, and the
tenant can manage how and if it will be deployed inside the defaults, like on
MCEs: which MCEs? Need to override values for a specific one? And configure
operators/<operator>/<operator>.yaml and values.yaml. Inside each cluster
this is the regular add-on configuration; it's different."

So there are two things, and 3.8 (ADR-0043) mixed them on one Addons page:

- an **operator**: a chart in a team's catalog (`operators/<op>/`) and the
  fleet defaults built from it (`defaults/<scope>/<op>/`), managed per team;
- an **add-on**: that chart on one cluster, managed from the cluster's page.

What the platform templates (`apps/day2-service/tests/oracle/platform/`)
offer for "which destinations" and "this one differently":

- **Which destinations.** A default reaches every destination of its scope
  the team registers, minus the names `defaults/<scope>/exclusions.yaml`
  lists under its chart. The operators chart turns the list into `exclude:`
  entries of the defaults generator. Excluding a destination deletes its
  wrapper Application; the platform's apps are `prune: false` with no
  resources finalizer, so the workload is **orphaned**, still running.
  Removing the entry generates the Application again, which adopts what
  still runs. The file explains itself in comments (the team's own copy is
  40 lines of comments and three of data). ADR-0022 deferred editing it for
  exactly that reason: a load and dump loses them.
- **Values for one destination.** `deployApp.yaml` layers
  `defaults/<scope>/<op>/values-<name>.yaml` above `values.yaml` and
  `values-<env>.yaml`, for every app of that chart on a destination of that
  name. The name is the MCE's (for an MCE hub) or the cluster's, not its
  path, so two destinations of the same name read the same file, and a
  destination named like an env (`prod`) would be the env layer.
- **Deploy config for one destination.** `operators.yaml` lists the
  deploy-config stack team default → OCP-version pin → fleet default
  (`defaults/<scope>/<op>/<op>.yaml`) → the destination's own
  `<clusterPath>/<op>/<op>.yaml`. There is **no per-destination layer in the
  defaults folder**. The only per-destination one is the destination's own
  folder, and a folder there is the XOR rule's duplicate unless the
  destination is excluded: the defaults README calls that pair "the
  deliberate full-override escape hatch, for when one MCE needs a different
  `repourl` / `targetRevision` rather than different values". Both
  generators name the wrapper app `<team>-<cluster>-<path.basename>`, so
  the move between them in one commit keeps the Application.

The review of 3.8.0 (2026-11-12) found, among others, that a write could
change or delete what a destination deploys without the person seeing it:
create put a team layer under clusters that had the chart in their own
folder and compared nothing; make default moved a cluster's own folder into
the default while a stale `exclusions.yaml` entry for it made its app vanish;
and a confirmation named cluster ids only, so a change landing between the
preview and the submit was opened unseen.

## Decision

**Operators get their own pages.** `/operators` → a team's
`/teams/<team>/operators` (its catalog, plus fleet defaults of charts not in
it) → `/teams/<team>/operators/<op>`: its `<op>.yaml` and `values.yaml`
(edited as 3.8 edits a team default, the deploy config in place), its
`ocp-versions/<v>/` pins (read-only), and one panel per scope (hosted
clusters, MCEs, the hub, UPI): is it a default there, make it one, edit it,
and every destination of that scope with how the default stands there
(`default`, `excluded`, `own-deploy`, `own-folder`, `duplicate`, `none`,
`not-rendered`). Destinations day1 or another team knows and this team does
not register are listed apart: a default does not reach them (ADR-0020). The
cluster page's Add-ons are unchanged. The authoring that lived in dialogs on
the Addons page moved here. The API keeps calling an operator an add-on
(`/addons/{team}/{addon}/...`).

**Exclusions are edited in place** (`domain.exclusions.set_excluded`), one
chart's list set to exactly the requested destinations: listed names keep
their line and place; new ones go after the last; a chart left with none
loses its key line (its comment lines stay); an `exclusions` left with no
chart reads `exclusions: {}`; a flow list (`[a, b]`) is edited on its line;
an absent file is created. Names the entry lists that are no destination of
the team stay as written (and stay a lint error). The result must parse to
the same document with only that list changed and keep every comment line in
order, else the edit is refused (`exclusions-layout`, with the reason):
tabs, a document marker, a flow-style `exclusions`, an item that is not a
name. This lifts ADR-0022's deferral. Two destinations of one name are
excluded together or not at all (`exclusion-shared`). Including a
destination that has its own deploy config is refused (`own-deploy`): it
would be the duplicate; removing the override includes it.

**Excluding says that it orphans, and must be confirmed.** The plan lists
the destination as `removed`, `orphaned`, with its Application's name; the
notes and the MR description say the workload keeps running unmanaged and
that teardown is by hand (runbook R10), as a per-cluster remove does.

**Per-destination values** are `values-<name>.yaml` in the default's folder,
created, replaced or (empty) deleted, guarded. Refused for the hub (its
default's `values.yaml` is the hub's own) and for a name that is an env.
Every destination the file reaches is in the impact. The web shows the
effective values before and after with provenance through `/merge-preview`
(its `override_values` previews exactly this file for a fleet-default app).

**Per-destination deploy config is offered through the carve-out**: one MR
adds the destination to the chart's exclusions entry and writes its own
`<op>.yaml` with only the keys asked (`targetRevision` — a branch of the
chart repo, warned as an emergency pin —, `repourl`, `path`,
`projectNamespace`); taking it back moves the own folder into the default
(as adoption does: a non-empty `values.yaml` becomes `values-<name>.yaml`)
and drops the entry. Its values still come from the default's layers below
its own folder's.

**Every authoring write measures its impact and is confirmed against its
preview.** After the platform lints (ADR-0023), Wingman compares every app of
the chart, on every destination of every kind, before and after: generated
or not, and its effective deploy config and workload values (chart defaults
aside, Helm's `null` kept as a value, flagged `after_null`, because it
deletes a chart default). An app that goes is `removed`, one that comes is
`added`, one that moves is `changed`. Every `removed` and `changed`
destination, and every adopted cluster whose move changes something or
loses an exclusion entry, must be named in `confirm_changes`, and the request
must carry the preview's `digest` (a sha256 of the MR's files — kind, path,
text —, its title, its impact and its adoptions) as `expected_digest`. A
request whose digest is not the plan's any more is refused, `409
REVISION_CONFLICT` `plan-changed`, with the new digest: the repo moved since
the preview, and the person has not seen what would now be opened. A change
landing in between that leaves the plan as it was does not refuse it. This
holds for 3.8's writes too (create, team default, make default, fleet
default).

**The review of 3.8.0, fixed here:**

1. *Create changed clusters unseen.* It is measured like every write: a
   cluster that had the chart in its own folder and whose deploy config or
   values move under the new team layer is listed key by key and confirmed;
   the note no longer says the catalog deploys nothing then. A team-default
   edit lists what it changes on every destination.
2. *A stale exclusion deleted an adopted cluster's app.* Until the default
   exists, an entry for its chart excludes nothing (and fails lint rule 1);
   once the folder is there it excludes the cluster, whose own folder has
   just moved into the default. Wingman **removes the entry in the same
   commit** and lists the cluster for confirmation (`exclusion_removed`), or
   refuses with the reason when it cannot edit the file exactly. Removing
   rather than refusing: the entry is stale by the platform's own rule, the
   person asked to make the chart a default, not to stop deploying it
   anywhere, and refusing would send them to edit by hand what Wingman can
   now edit exactly. The generic impact check backs it: any app that would
   go is `removed` and must be confirmed.
3. *Confirmation was not tied to the preview*: the digest above.
4. *An in-place edit dropped unrelated comments* (a file header above the
   first key, the indented last comment of the block before). A removed key
   now takes its own lines only, never a comment line, and the safety check
   requires every comment line of the old text, in order.
5. *A `null` in fleet values was not a change*: it is, with `after_null`.
6. *Access reads failed all at once*; *7. access through a group share read
   as "not a member"*; *the fake never answered 404 for a private project*;
   *`sync_settings` misread `automated: {enabled: false}` and
   `automated: true`*: see Amendments.
8. *A values file deleted after the read was created again*: a write whose
   file is gone but existed at the caller's `last_commit_id` is a 409.

Nits: the template's tie goes to the platform default only when it leads;
`ignoreDifferences: []` removes the key; adoption refuses a
`values-<name>.yaml` that would be an env layer or that exists already (two
destinations of one name); `refuse_new_errors` reads `exclusions.yaml` as the
change leaves it (it read the old text, so an exclusions edit was linted
against the wrong file). Kept: a changed scalar keeps its line's comment
even when the comment may be stale (`syncPolicy: null  # manual`), because
Wingman cannot tell a stale comment from a true one and dropping it loses
information; the MR diff shows the line.

New MR verbs (ADR-0007): `Exclude`, `Include`, `Override`; actions
`set-exclusions`, `override-values`, `override-deploy`. The web-visible API:
`docs/notes/2026-11-12-operators-page-api.md`.

## Alternatives rejected

- **Exclusions by load and dump.** It drops the file's comments; ADR-0022
  deferred the feature rather than do that.
- **A generic in-place YAML edit (`yaml_text`) for exclusions.** It rewrites
  a changed list whole and refuses a comment inside it; exclusions lists
  carry per-name comments ("until 2026-12"), so the list is edited line by
  line instead.
- **Refusing make default over a stale exclusion.** See 2 above.
- **Keeping the excluded cluster's own folder (the carve-out) instead.** The
  person did not ask for a full override, and the default's value layers
  would still change its values.
- **A per-destination deploy-config file in the defaults folder
  (`<op>-<name>.yaml`).** The platform has no such layer; Wingman would
  write a file nothing reads.
- **Confirming ids only, or a guard sha of the whole repo.** Ids do not say
  what was seen; a repo sha refuses every unrelated commit in between. The
  digest refuses exactly when what would be opened differs from what was
  shown.
- **Registering an unregistered MCE from the scope panel.** A folder for it
  makes every fleet default of the team reach it; that is its own decision,
  not a checkbox of one operator.

## Consequences

- Every authoring write is two requests from the web (preview, confirmed
  submit), as 3.8's make default already was. An API client that skipped the
  preview now gets 422 `confirm-changes` or `confirm-against-preview` when
  the write deletes or changes what a destination deploys.
- A team-default or fleet-default edit lists every destination it changes;
  on a large fleet that list is long, and it is meant to be read.
- An exclusions file in a layout Wingman cannot edit exactly is shown with
  the reason and its checkboxes disabled; a person edits it by hand.
- Left for later: stopping being a default (ADR-0043); authoring
  `ocp-versions/` pins; per-destination sync options.

## Amendments

**2026-11-13, 3.13.0: no exclusions in Wingman; a subset of MCEs is
per-MCE installs; hosted-cluster specifics belong to flavors and create.**
The user, on reviewing the fold (PR #38): "There is no exclude option inside the defaults —
there is only the option to override values for specific MCEs. If we want
something only on specific MCEs, it means creating a file inside their
folders. About the HCs: the default add-on for everyone is there, but the
specific ones are for the flavor and the create-cluster form, not ours." So,
superseding the exclusion and carve-out parts of the decision above:

- **Wingman writes no `exclusions.yaml`.** The destination checkboxes, the
  orphaning-by-exclusion flow and `PUT /addons/{team}/{addon}/defaults/{scope}/exclusions`
  are gone. The file is still read wherever the platform reads it (the
  simulation, the lints, the page's states: a repo that has one renders and
  shows as it is), and 3.12.0's adoption fix stays: making an add-on a
  default still drops a stale entry that would delete an adopted cluster's
  app. `domain.exclusions.set_excluded` stays for that.
- **The per-destination deploy-config carve-out is gone** (`PUT .../destinations/{cluster}/deploy`):
  it was built on exclusion.
- **Values per env and per destination, on the MCE, hosted-cluster and
  UPI defaults alike.** The user, the same day: "There are also HC defaults,
  and they work the same idea as the MCE"; the platform's own READMEs agree
  (`defaults/hosted-clusters/` is "the hosted-cluster mirror of
  defaults/mces/", and `defaults/upi/` the same). Each of the three layers,
  lowest first, the default's `values.yaml`, `values-<env>.yaml` (prod, prep
  or test: `PUT .../defaults/{scope}/envs/{env}/values`) and
  `values-<name>.yaml` (one MCE, hosted cluster or UPI cluster:
  `PUT .../defaults/{scope}/destinations/{cluster}/values`), below the
  destination's MCE-wide or UPI-wide and cluster-wide files: env before
  cluster, and the cluster wins (`domain.stacks`, checked by the oracle;
  an env override is rendered by it too). The effective values before and
  after come from `/merge-preview`, which takes an `override_path` for an env
  file, previewed on a destination of that env. The hub is one destination,
  its default's own values (`override-scope` refuses it).
- **Deploy on specific MCEs** is new, on the MCE panel of an add-on's page
  (`POST /addons/{team}/{addon}/mce-installs`). An add-on wanted on some MCEs
  only is not a default: it is installed in each chosen MCE hub's own
  `sites/<site>/<env>/mces/<mce>/in-cluster/<chart>/`, by ADR-0022's install
  (`values.yaml`, and `<chart>.yaml` only when a key is needed), one MR per
  MCE, as the per-cluster principle of ADR-0044 asks. They are opened four at
  a time; each MCE is planned, refused (installed already, not rendered, or an
  MCE default of the add-on: the XOR rule, with the reason) or failed on its
  own; nothing is retried, and once GitLab does not answer no more are
  started. A dry run plans each. Where it is installed is listed per MCE with
  the usual remove and its orphaning warning. An MCE the team's repo does not
  register yet can be chosen: installing registers it, so the team's MCE
  defaults reach it too, and the plan says so.
- **The hosted-clusters panel** works like the MCE one (the default, its
  values per env and per cluster) without deploying on specific hosted
  clusters: which add-ons a hosted cluster has of its own comes from its
  flavor and the create form (a link to Flavors). A cluster's own page is
  unchanged.
- Messages that suggested excluding (the XOR refusal of an install, the
  refusal to pin or remove a fleet default on one cluster) say what to do
  instead. Core keeps `Verb.EXCLUDE` and `Verb.INCLUDE`, so the titles of MRs
  3.12 opened still parse (ADR-0007).

**2026-11-12, released in 3.13.0: the Operators page is folded into Addons; one place,
called add-ons.** The user, on seeing 3.12.0: "operators IS addons", and "we
already had it: Addons can control defaults, it just can't control
overrides". The separate Operators section split one thing in two and named
it twice. So:

- There is no Operators entry, page or label. A day2 add-on is an *add-on*
  everywhere in the UI; `operators/` appears only as the folder name in a
  team's repo, where a file path is shown.
- The **Addons** page has its authoring back, as 3.8.0 had it: *New add-on*
  on each team (the form is `/addons/new?team=<team>`: a query, so an add-on
  may be named `new`), and *Edit team default* on each add-on.
- What 3.12.0 added is on the add-on's own page, reached from the Addons page
  (*Defaults & overrides*, `/addons/<team>/<chart>`): per scope, make it a
  default and edit that default, *which destinations* (the checkboxes that
  edit `exclusions.yaml`, with the orphaning confirmation), and per
  destination its values (`values-<name>.yaml`) and its own deploy config.
  The page is the one 3.12.0 built, moved and renamed.
- 3.12.0's routes redirect, so links keep working (`next.config.ts`, 307):
  `/operators` to `/addons`, `/teams/<team>/operators` to
  `/addons?team=<team>`, `/teams/<team>/operators/<chart>` to
  `/addons/<team>/<chart>`, `/teams/<team>/new-operator` to
  `/addons/new?team=<team>`.
- The reads are `GET /teams/{team}/addons` and
  `GET /teams/{team}/addons/{addon}`; 3.12.0's `/teams/{team}/operators[...]`
  stay as deprecated aliases with the same answers. Every write, MR,
  confirmation, digest and review fix of 3.12.0 is unchanged. The service's
  refusal to remove a fleet default from a cluster points at the add-on's
  page (`details.addon`), keeping `details.operator`.
- One cluster's add-ons, on its own page, are unchanged.

The review's access and sync-settings findings, fixed in the same change:

- **6. Access is read per team.** A team whose access GitLab does not answer
  is read as access unknown: read-only, `writable: false`,
  `access_role: "unknown"`, `access_level: 0`, its reason naming the project
  and the cause. Every write for it is refused with `403 TEAM_READ_ONLY`, and
  the other teams read as usual (one failing `GET /projects/:id` used to fail
  `/teams`, `/addons` and `/fleet-defaults` for everyone). The failure is not
  cached (the cache keeps only answers), so the next read asks GitLab again.
  The web fails closed too: a team whose access it has not read is offered
  no write.
- **7. Group shares count.** `access_level` is the highest of the account's
  project membership, its membership of the project's group or a group above
  it, and each group the project is shared with (`shared_with_groups`),
  where a share gives the lower of the share's role and the account's own
  role in that group, inherited roles included
  (`GET /groups/:id/members/all/:user_id`). GitLab's `permissions` leaves
  shares out (both `null` on CE 19.5.3), so a team that opted in by sharing
  its project with a group Wingman's account is in read as "not a member".
  The extra reads happen only for shares that could raise the level, inside
  the `access_level` operation, so the metric labels do not change. Not
  modelled: a share of the project's *namespace* group with another group.
- **A project the account cannot see** (GitLab's 404 for a private project
  it has no access to) reads as no access (level 0, `none`), not as unknown,
  and is kept like any answer. The fake now answers 404 there too, and the
  contract suite holds both to it.
- **Sync options are read as ArgoCD 3 reads them**: `automated` set and its
  `enabled` absent or true is auto-sync, so `automated: {enabled: false}` is
  manual sync (ArgoCD's off switch, kept as written when a team default stays
  manual). An `automated` that is not a map (`automated: true`), or a
  non-boolean `enabled`, is refused by the Application CRD: it reads as
  manual sync and is the new lint error `sync-policy-invalid` on the layer
  that sets it (Wingman's own rule, ADR-0023). Wingman's team-default and
  fleet-default writes always give exactly the asked settings and a policy
  ArgoCD takes (`enabled: true` over a switched-off layer, `automated: null`
  over a refused one).

## Verification

The 2026-11-12 fold: `apps/web/e2e/tests/addon-defaults.spec.ts` (an
add-on's page reached from Addons, no Operators entry, 3.12.0's routes
redirecting) and `addon-authoring.spec.ts` (New add-on and Edit team default
on the Addons page); `tests/api/test_operators_api.py` (the
`/teams/{team}/addons` paths and their 3.12.0 aliases answer the same).


- `tests/unit/domain/test_exclusions_text.py`: the fixture's 40 comment
  lines kept on add, remove, a new chart, the last name gone; flow lists;
  comments inside a list; each refused layout and its reason.
- `tests/unit/domain/test_yaml_text.py`: a file header and the last comment
  of the block before stay when a key is removed.
- `tests/unit/application/test_fleet_targets.py`: exclude (orphan, confirm,
  the file one line longer), include, a new chart entry, refusals, a preview
  the repo moved away from (409) and one it did not, values overrides
  created and deleted guarded, an own deploy config and back with the same
  wrapper apps.
- `tests/unit/application/test_authoring_review.py`: review items 1, 2, 5,
  8 and the nits, each a regression test.
- `tests/oracle/test_render_chain_oracle.py`: `render_chain.py` renders an
  exclusion as exactly one app gone, an inclusion as it back, a values
  override as that destination's values changed only, an own deploy config
  as the same apps with that leaf's `targetRevision` only, the stale-exclusion
  make default with every app kept, and a create whose changes to an existing
  folder are the ones Wingman lists.
- `tests/api/test_operators_api.py`: the reads, the confirmations and the
  409 through HTTP.
- Amendments: `tests/unit/application/test_access.py` and
  `tests/api/test_access_api.py` (one team's failing access read),
  the GitLab contract suite (shares, a private project's 404; 46/46 on the
  fake and on GitLab CE 19.5.3, ADR-0005), `tests/unit/domain/test_sync_policy.py`
  (hypothesis properties over policies as people write them) and
  `tests/unit/application/test_sync_policy_lint.py`.
