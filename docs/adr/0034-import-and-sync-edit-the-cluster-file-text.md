# ADR-0034: Existing clusters join a flavor by one MR that writes only the link; Wingman edits a cluster file's text, never a YAML round trip

Date: 2026-11-08
Status: Accepted

## Context

Flavors v2 (user decisions of 2026-11-08) lets existing clusters, written by
hand before Wingman, join a flavor: an import writes the flavor link into
the picked files, and after the merge they show their differences as drift
(ADR-0033). A cluster file has several writers (ADR-0012): people and their
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
ADR-0033) and says whether it can join: `ready`, `relink` (it follows
another flavor), `linked` (it follows this one: sync it instead) or
`refused` (its file cannot be edited safely). `POST /specs/{name}/import`
opens one day1 MR (`[Wingman/Day1] Import spec <flavor> into <n> clusters`,
at most 50) whose one commit gives each file the header with `specName` and
`specVersion` and changes nothing else. A cluster that follows another
flavor is refused unless its pick says `relink: true`; then the old header
is replaced, keeping the add-on values requested before for add-ons the new
flavor also lists. Each file update carries the `last_commit_id` the preview
showed: a file that moved since fails the whole import, before or at the
commit (ADR-0006), and nothing is opened. The MR description lists each
cluster with what will show as drift after the merge.

**The port.** Import is a cluster change, so it goes through
`ClusterProvisioner` (ADR-0017) as `link`, beside `apply`.

## Alternatives rejected

- **A round-trip YAML library** (ruamel): still reflows long lines and
  quoting in places, and the CI block would be rewritten by a parser that is
  not the CI's. A new dependency for less safety.
- **Write the link elsewhere** (a sidecar or a Wingman-owned file): every
  file under `hostedClusters/` becomes an Argo Application (ADR-0012).
- **One MR per cluster**: the user's decision is one day1 MR; a reviewer
  sees the whole import in one place.
- **Re-link silently**: moving a cluster from one flavor to another changes
  what its locks are; the request has to say so.

## Consequences

- Imported clusters are linked when the MR merges, and show their
  differences as drift; nothing on a cluster changes at import.
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
  commit, the title, branch and footer, and a stale file committing nothing.
- `apps/day1-service/tests/api/test_flavor_links_api.py`: the JSON.
