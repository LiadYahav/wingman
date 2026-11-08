# ADR-0026: A flavor lock is a fixed value the flavor enforces

Date: 2026-11-08
Status: Accepted

## Context

A spec ("flavor" in the UI, ADR-0013) presets template inputs in
`spec.day1.values` and marked fields with `immutable_paths`. That list was a
form hint ("can't change after create"): nothing enforced it, and the
editor saved paths without values, so a "locked" field fixed nothing. User
decision 2026-11-08 (flavors v2, `docs/ideas/flavors-v2.md`): **a lock is a
fixed value in the flavor.** A locked field takes the flavor's value, a
create can't override it, and (stage 2) a later edit that changes it shows
as drift. An unlocked value is a preset anyone can override at create.

## Decision

**Presets and locks.** Every value in `spec.day1.values` is a preset
(prefilled, merged under what the create sends) unless its path is in
`spec.day1.locked_paths`.

**The field is renamed, with the old name read as an alias.**
`locked_paths` says what the list now means. `immutable_paths` is still
read, from spec files already in GitLab and from request bodies, as the
same list; it is never written or returned. A document with both is
refused. A spec saved again is stored with the new name.

**Paths are template-input paths** (`wingman_day1.domain.locks`):

    path  := name ( "." name | "[" index "]" )*
    name  := [A-Za-z_][A-Za-z0-9_]*
    index := "0" | [1-9][0-9]{0,2}

at most 253 characters (`owner_merkaz`, `nodepools[0].configs`). This is
the syntax the web form already used for `immutable_paths`.

**Only what drift can compare is lockable.** Each lockable input, and the
cluster-file key the shared template writes it to, is one row of
`LOCKABLE` in the domain, next to the template code, for stage 2's drift:

| Template input | Cluster-file key |
|---|---|
| `owner_merkaz`, `owner_anaf`, `owner_mador` | `owner.merkaz`, `owner.anaf`, `owner.mador` |
| `platform` | `platform` |
| `nodepools[<i>].replicas` | `nodepool[<i>].replicas` |
| `nodepools[<i>].configs` | `nodepool[<i>].configs` (network entries expanded, ADR-0027) |
| `nodepools[<i>].node_labels` | `nodepool[<i>].nodeLabels` |

The inputs Wingman sets per cluster (`cluster_name`, `site`, `mce`,
`openshift_release_version` and the aliases `site_name`, `mce_name`) are
never lockable. The OpenShift version is chosen per cluster at create (user
decision); a flavor that presets `openshift_release_version` keeps it as
the create form's default, as before.

**At save** (`POST /specs`, `PUT /specs/{name}`) each locked path must
parse, be lockable, be listed once, and have a value in `spec.day1.values`
(a lock without one fixes nothing); at most 100 locks. Every broken rule is
a line of the 422's `details.problems`.

**At create** (and preview), a request that sends a value other than the
locked one for a locked path is a 422 naming the path, the flavor's value
and the sent one. A request may leave a locked path out, or send a list
that replaces the one the lock sits in (lists are not merged, ADR-0013):
the flavor's value is put in place either way. A lock on a nodepool
position the request does not have (`nodepools[1].replicas` with one
nodepool) is a 422. Values compare as JSON, except that a whole number and
the string of its digits are equal (the template writes both the same way,
and the current form sends numbers it edits as text); `true` is not `1`.

**Specs already in GitLab keep loading.** A stored lock that breaks the
save rules (a reserved input, a shape that is not lockable, no value) is
not enforced, and the API lists it in the spec's `warnings`, with every
other save rule the stored spec breaks.

**Locks are by position in stage 1.** `nodepools[0].configs` means the
first nodepool. How a flavor's nodepool locks apply to an imported cluster,
whose nodepools come in any number and order, is stage 2's decision.

## Alternatives rejected

- **Keep the name `immutable_paths`**: the meaning changed (a fixed value
  enforced at create, not a hint about later edits), and the old word is
  what the user wanted gone.
- **Rename without an alias**: every spec in GitLab, and the web form that
  sends `immutable_paths` today, would break at once.
- **Refuse a create that leaves a locked value out**: the person creating
  the cluster would have to resend a value they cannot change.
- **Allow any path**: stage 2 could not compare a locked input that has no
  cluster-file key, and a lock on a part of a list (`configs[1]`) would not
  match what the CI renders, which is the whole list.

## Consequences

- The create form shows locked values read-only and may send them or leave
  them out; it should prefill presets.
- `GET /specs` and `GET /specs/{name}` return `spec.day1.locked_paths` and
  `warnings` (`docs/notes/2026-11-08-flavors-v2-api-changes.md`).
- Stage 2 builds day1 drift on `LOCKABLE` and `enforced_locks`.

## Verification

- `apps/day1-service/tests/unit/domain/test_locks.py`: the path grammar
  (with a round-trip property test), lookup and assignment, the lockable
  table and its file keys, the save rules, enforcement and comparison.
- `apps/day1-service/tests/unit/domain/test_specs.py`: the alias, both names
  refused, stored specs that break the rules, the fixture flavor
  `agent-dell`.
- `apps/day1-service/tests/unit/application/test_flavor_rules.py` and
  `apps/day1-service/tests/api/test_flavor_rules_api.py`: locked values put
  back, conflicts and missing nodepools refused, presets overridable, legacy
  locks not enforced, and the API's 422s and `warnings`.
