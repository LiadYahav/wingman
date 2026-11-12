# ADR-0037: Existing clusters join a flavor by one MR that writes only the link, and sync to it by one MR each; Wingman edits a cluster file's text, never a YAML round trip

Date: 2026-11-08
Status: Accepted; superseded in part by ADR-0044 (an import opens one MR per cluster)

Since ADR-0044 (2026-11-12, the architect's decision, confirmed by the
user) an import opens one day1 MR per picked cluster, each the link-only
change for its file, after every pick is checked as below. The text edit,
the statuses, relink, the stale check and sync still hold. The parts that
changed are marked where they are.

## Context

Flavors v2 (user decisions of 2026-11-08) lets existing clusters, written by
hand before Wingman, join a flavor: an import writes the flavor link into
the picked files, and after the merge they show their differences as drift
(ADR-0036). A cluster file has several writers (ADR-0012): people and their
comments, Wingman, the allocate-segment workflow (`vlanId`, `dhcp_values`)
and the day1 CI, which appends a block under `# === Added by CI ===`
(`mcFiles`, `mcConfigMap`). The platform-config CI edits these files line by
line for that reason, and checks that its result renders the same values. A
YAML load and dump would reflow and re-quote the file, drop every comment,
and rewrite the CI's block. Nothing in the repo edited a YAML file in place:
day2 writes whole small files, and the legacy `wingman_shared.yaml_utils`
round-trips through ruamel (and new code may not import it).

## Decision

**Text edits, checked.** `wingman_day1.domain.cluster_text` edits lines, as
the platform's own scripts do, with no new dependency:

- `with_header` sets Wingman's header (`# specName`, `# specVersion`,
  `# wingmanAddons`) in the leading comment block: header lines are replaced
  where the first of them is, or put first; no other line changes.
- `edit_values` sets locked values: `owner.<x>`, `platform`, a nodepool's
  `replicas`, `nodeLabels` and `configs`. A replaced value keeps its line's
  comment. A config entry that stays keeps its line, in the file's order; a
  removed one takes only its own lines; new entries go after the last kept
  one, in the indentation the file already uses (production's compact `- `
  or the template's indented one). New keys never go above the leading
  comment block, where the header must stay.
- Every edit checks its own result before it is returned: the text must
  parse, hold exactly the old values with the intended changes (types and
  all: `"3"` is not `3`), keep every line from the CI marker on byte for
  byte, and keep every comment line outside a removed entry. A header edit
  must also leave every line but the header's identical. A layout the editor
  does not handle (a flow-style `nodepool`, a value spread over lines, a key
  below the CI marker) is refused with the reason (422), never written
  approximately; a person edits that file by hand.
- Nothing edits `vlanId`, `dhcp_values`, `mcFiles` or `mcConfigMap`, or any
  line at or below the CI marker.

**Import.** `POST /specs/{name}/import/preview` compares each picked
cluster with the flavor (value drift, missing add-ons, version differences;
ADR-0036) and says whether it can join: `ready`, `relink` (it follows
another flavor), `linked` (it follows this one: sync it instead) or
`refused` (its file cannot be edited safely). `POST /specs/{name}/import`
opens one day1 MR (`[Wingman/Day1] Import spec <flavor> into <n> clusters`,
at most 50) whose one commit gives each file the header with `specName` and
`specVersion` and changes nothing else. *(Superseded by ADR-0044: one MR
per cluster, `[Wingman/Day1] Import cluster <name> into spec <flavor>
v<version>`, each changing only its file's header.)* A cluster that follows another
flavor is refused unless its pick says `relink: true`; then the old header
is replaced, keeping the add-on values requested before for add-ons the new
flavor also lists. Each file update carries the `last_commit_id` the preview
showed: a file that moved since fails the whole import, before or at the
commit (ADR-0006), and nothing is opened. The MR description lists each
cluster with what will show as drift after the merge. *(Superseded by
ADR-0044: a file that moved before the check still opens nothing; one that
moves between the check and its commit fails only its own MR, and each
MR's description shows its own cluster's drift.)*

**Sync.** `POST /clusters/{name}/sync/preview` shows what one day1 MR
would change on a linked cluster: every locked value its file does not hold
(ADR-0036) set to the flavor's, and the header's `specVersion` moved to the
flavor's current version; the diff; each config it removes; and each
nodepool whose configs change. Presets are never synced, and missing add-ons
are listed for the web to install through day2 (ADR-0016: day1 never writes
day2). `POST /clusters/{name}/sync` opens the MR
(`[Wingman/Day1] Sync cluster <name> to spec <flavor> v<version>`):

- **Removals are confirmed.** The rule is exact (ADR-0029), so a sync can
  remove configs. The request must name exactly the preview's removals in
  `confirm_removals`, or it is refused; the MR description names them too.
- **The roll is stated.** Changing a nodepool's configs rolls its nodes. The
  preview and the MR say how, from the nodepool's own keys: drained and
  rebooted in place, one node at a time or `inPlace.maxUnavailable` at a
  time (the chart's default `upgradeType` is `InPlace`), or replaced with new
  nodes (`upgradeType: Replace`).
- **Wingman never guesses hardware.** A nodepool with no network config, or
  several, blocks the sync until the request chooses its hardware type
  (`hardware: [{nodepool, hardware}]`), checked like a create (ADR-0027). A
  locked position the file does not have blocks it until a person edits the
  file.
- **Guards.** The request carries the preview's `last_commit_id` (the commit
  the repo was read at, ADR-0035) and flavor version. The sync is stale only
  if this file changed since that commit or the flavor moved; the write
  carries the commit, so GitLab refuses a file that moves in between
  (ADR-0006).
- **A file with an explicit `mcFiles`** renders only what it names. Wingman
  never writes `mcFiles`, so the preview warns when a config the sync adds is
  not listed there.

**The port.** Import and sync are cluster changes, so they go through
`ClusterProvisioner` (ADR-0017): import as `link`, sync as `apply` with the
`sync` action. *(Superseded by ADR-0044: import is `apply` with the
`import` action too; `link` is gone.)*

## Alternatives rejected

- **A round-trip YAML library** (ruamel): still reflows long lines and
  quoting in places, and the CI block would be rewritten by a parser that is
  not the CI's. A new dependency for less safety.
- **Write the link elsewhere** (a sidecar or a Wingman-owned file): every
  file under `hostedClusters/` becomes an Argo Application (ADR-0012).
- **One MR per cluster**: the user's decision is one day1 MR; a reviewer
  sees the whole import in one place. *(Superseded: ADR-0044 chose it, the
  architect's decision confirmed by the user on 2026-11-12, so that each
  cluster's link is reviewed, merged or rejected on its own.)*
- **Re-link silently**: moving a cluster from one flavor to another changes
  what its locks are; the request has to say so.

## Consequences

- Sync fixes exactly the value drift that needs no decision, in one MR per
  cluster; after it merges the cluster is in sync on its locked values, and
  the web installs its missing add-ons through day2.
- A sync that removes configs, or rolls nodes, says so three times: the
  preview, the confirmation the request must carry, and the MR description.
- Imported clusters are linked when the MR merges, and show their
  differences as drift; nothing on a cluster changes at import. (Since
  ADR-0044, each when its own MR merges.)
- Two imports of the same cluster can both be opened; once one merges the
  other conflicts in GitLab, which refuses to merge it.
- A file whose layout the editor refuses must be fixed by hand before it
  can be imported.

## Verification

- `apps/day1-service/tests/unit/domain/test_cluster_text.py`: exact
  before/after texts on both fixture styles, comments, CRLF and a missing
  final newline, each refusal, and a property test that any configs edit
  changes only the configs and keeps the CI block.
- `apps/day1-service/tests/unit/application/test_imports.py`: the preview's
  statuses and drift, the byte-for-byte import, relink, a moved file or
  flavor, an unparsable file.
- `apps/day1-service/tests/unit/infrastructure/test_merge_requests.py`: one
  commit, the title, branch and footer, and a stale file committing nothing
  (per cluster since ADR-0044).
- `apps/day1-service/tests/unit/application/test_sync.py`: the exact
  synced text on both fixture styles, hardware choices, the removals to
  confirm, how a nodepool's nodes roll (`InPlace`, `maxUnavailable`,
  `Replace`), the `mcFiles` warning, a stale file or flavor, another file
  changing (not stale), nothing to sync, a header-only version move.
- `apps/day1-service/tests/api/test_flavor_links_api.py`: the JSON of drift,
  import and sync.
