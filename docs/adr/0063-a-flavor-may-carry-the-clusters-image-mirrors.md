# ADR-0063: A flavor may carry the cluster's image mirrors, written only when given, and a template that does not write them is refused

Date: 2026-11-18
Status: Accepted

## Context

The hostedclusters-setup chart builds a HostedCluster's
`imageContentSources` from two lists of `{source, mirrors}`: the MCE values
layer's `defaultImageContentSources` and the cluster file's own
`imageContentSources`. It puts them together, merges the entries of one
source (their mirrors joined) and sorts them by source. A cluster file with
`disableIdmsMerge: true` gets only its own list, and the MCE's are dropped
(`docs/ecosystem/notes/hosted-clusters.md` §2.2).

Some customers deploy operators of their own and pull them from their own
registry destinations (the user, 2026-11-18): their clusters need mirrors
of their own, and some need only those. A flavor could express neither, so
such a cluster could not be created from a flavor, and its flavor could not
hold the mirrors it needs. The user wants it optional.

Two constraints shaped the answer:

- **The template is the specs project's own.** A flavor's values are
  inputs of `cluster-template.j2` (ADR-0013), and the production specs
  project has its own template. Rendering with `StrictUndefined` refuses an
  input the template reads but is not given; an input that is given but not
  read is dropped without a word. A flavor with mirrors against a template
  that does not read them would create clusters without them.
- **New features land in the air-gap off.** A flavor without mirrors, and
  every cluster file today, must render and drift exactly as before.

## Decision

**Two optional template inputs**, top-level, each written to its key only
when given:

| Template input | Cluster-file key | Value |
|---|---|---|
| `image_content_sources` | `imageContentSources` | a list of `{source, mirrors: [..]}`: the cluster's own mirrors |
| `disable_idms_merge` | `disableIdmsMerge` | `true`: only those mirrors; the MCE's default mirrors are dropped |

Absent, `[]` and `false` write nothing, so the MCE's mirrors apply as
before; the fixture template renders a file without them byte for byte as
it did. An entry has exactly `source` and one or more `mirrors`: no space,
no URL scheme, not starting with `-`, and the safe-value rule every input
has (ADR-0013). A source is listed once (the chart would merge a repeated
one; one entry per source keeps the flavor readable and the drift exact),
a mirror once per entry. `disable_idms_merge` is a JSON boolean: the
string `"false"` would be true to Helm. The rules hold at a flavor's save
(422), on a stored flavor (its `warnings`) and at a create (422).

**No mirrors at all is refused, not warned.** `disable_idms_merge: true`
with no entries of the cluster's own would give the HostedCluster no
mirrors: in a disconnected environment it could pull neither its release
nor its operators, and no cluster needs that. A save, a stored flavor's
warnings and a create all say so; with a preset list, the create checks the
list it is sent.

**Preset or locked, drift and the per-cluster MRs.** Both inputs are
lockable as whole values (a row each in `LOCKABLE`, amending ADR-0026's
table); a lock whose value breaks the rules above is not enforced, and the
flavor's warnings say why, as for every lock (ADR-0026). Drift (ADR-0036)
compares them as the chart uses them: the list by its entries merged by
source and sorted, a missing key being no entries; `disableIdmsMerge` by
Go's truth, a missing key keeping the MCE's. A flavor's merge request for
each cluster (ADR-0037, ADR-0044) writes them in the file's text: an
existing key keeps its line, its comment and the comments in its block,
and its old content is replaced by a block list as the template writes it;
a new key goes above `nodepool`.

**A template that does not write them is refused, twice.**

1. At a flavor's save, a flavor that gives mirrors (a non-empty list, or
   `disable_idms_merge: true`) is refused while the shared template does
   not read the input. "Reads" is `analyze_template`, the analysis the
   create form's schema comes from. A stored flavor shows the same problem
   in its `warnings`, on its page and on the create form. A save without
   mirrors does not read the template at all.
2. At a create (its preview, and the provision-cluster workflow's start),
   the rendered file must hold exactly the mirror inputs given, compared as
   the chart uses them, as ADR-0061 checks `tuningConfig`. Inputs not given
   are not checked, so a template that writes mirrors of its own still
   renders a flavor without them.

Both messages name `docs/upgrade/3.44-to-3.45.md`, which gives the operator
the template lines. The first tells the person writing the flavor before
any cluster is touched; the second holds for a create that sends the
inputs itself, and for a template that reads them but writes them wrong.

## Alternatives rejected

- **A warning for a stale template.** A flavor saved with mirrors that
  every create then drops is the failure this decision exists to prevent.
- **Wingman writing `imageContentSources` outside the template.** A second
  writer of the cluster file beside the template the team owns (ADR-0013).
- **A setting to turn the feature on.** Absent inputs already change
  nothing; a setting would add a switch with nothing behind it.
- **A lock per entry** (`image_content_sources[0]`), or one input for the
  list and the switch together. Positions mean nothing to the chart, and
  the switch is a decision of its own: a flavor may lock the switch and
  leave the list a preset.
- **Comparing the list in order.** The chart merges and sorts it, so two
  orders are the same cluster.
- **A warning for "no mirrors at all".** See the decision.

## Consequences

- An operator adds the template lines to the specs project's
  `cluster-template.j2` before saving a flavor with mirrors
  (`docs/upgrade/3.44-to-3.45.md`). Until then such a save is refused and
  nothing else changes.
- A flavor that locks the list fixes the cluster's own mirrors exactly: a
  file's extra entries drift, and its merge request replaces them. A preset
  list is never compared.
- `extraImageRegistries` (the HostedCluster's allowed registries, beside
  the mirrors) is not a flavor input. It would be another input of the same
  kind, decided on its own.
- The web shows them in the flavor editor's Basics, on the flavor's
  Overview (Cluster inputs) and on the create form, preset or locked, and
  in drift.

## Verification

- `apps/day1-service/tests/unit/domain/test_image_mirrors.py`: the rules,
  the template guard (a template without the lines refuses and warns, an
  empty or broken one is left to the create), the fixture template's output
  with and without mirrors (byte for byte the old one without), the chart's
  view (merge, sort, Go's truth), locks, drift and the text edits.
- `apps/day1-service/tests/api/test_image_mirrors_api.py`: save, the 422s, a
  stored flavor's warnings, a create with and without mirrors against both
  templates, and a sync that writes them.
- `apps/day1-service/tests/unit/domain/test_template.py` (the fixture
  template's schema) and `test_locks.py` (the lockable table).
- With a hostedclusters-setup chart, `WINGMAN_TEST_CHART_DIR` runs
  `tests/api/test_fixture_template_contract.py` through `helm template`.
