# ADR-0044: Importing clusters into a flavor opens one MR per cluster, checked all together first, opened four at a time

Date: 2026-11-12
Status: Accepted (supersedes in part ADR-0037: one MR for the whole import)

## Context

ADR-0037 opened one day1 MR for an import: every picked cluster's link in
one commit, so a reviewer saw the whole import in one place. The
architect's decision, confirmed by the user on 2026-11-12, is the
opposite: "Each cluster gets its own merge request — also in import, it's
important." One MR for fifty clusters is all or nothing. One cluster's
owner objecting holds back the other forty-nine. A commit on main to one
of the files (a person, the CI, the allocate-segment workflow) makes the
whole MR conflict. Taking one cluster out means editing the MR by hand.
Every other day1 write was already one cluster per MR (create, modify,
delete, sync), and the MR conventions name one resource (ADR-0007).

## Decision

**Check everything first, as before.** The flavor's version, the stale
check (`changed_since` against the preview's `last_commit_id`, ADR-0035)
and each pick's status (`refused`, `linked`, `relink` without `relink:
true`) run for every pick before anything opens. One refused pick is a
422 and one moved file a 409, and no MR opens.

**Then one MR per cluster.** Import becomes a cluster change like sync:
`ClusterProvisioner.apply` with the new `ClusterAction.IMPORT`. The port's
`link` and `ImportChange` are gone. Each MR is the link-only change for
its one file (the header, and nothing else, ADR-0037), through
`mr_conventions` (ADR-0007):

- title `[Wingman/Day1] Import cluster <name> into spec <flavor> v<version>`
  (it was `Import spec <flavor> into <n> clusters`);
- branch `platform/<user>/import-cluster-<name>-<UTC stamp>`; the
  cluster's name keeps apart the MRs an import opens in the same second;
- footer `Action: import`, `Resource: cluster/<name>`; labels `wingman`,
  `day1`, `import`;
- a description about that cluster only: its site and MCE, the flavor it
  was re-linked from if any, and what will show as its drift once merged
  (each locked value the file does not hold, each missing add-on).

**Four at a time, reported in pick order.** Each MR is a commit and an MR
on GitLab, about a second. Fifty in a row can outlast the proxy's
`proxy_read_timeout` of 60 s, and a request the proxy cuts while day1 goes
on opening invites a retry that opens every cluster's MR twice. Fifty at
once is fifty concurrent commits on one project. Four
(`MAX_OPEN_CONCURRENCY`) keeps a full import near fifteen seconds.

**Each failure is its cluster's.** A file that moved between the check and
its commit (`RevisionConflictError`), or a write GitLab refuses, fails
that MR; the others open. An `AmbiguousWriteError` (GitLab did not confirm
the write, so the MR may exist) is reported for that cluster and never
retried (ADR-0006). Once GitLab is unreachable or leaves a write
unconfirmed, no further MR starts: each one not started is reported as not
sent (a `GitUnavailableError` naming the cluster GitLab did not answer
for). Waiting out a 20 s read timeout per remaining cluster would hold the
request past the proxy's timeout, the case the concurrency avoids.

**The answer.** `POST /specs/{name}/import` answers 201 with
`merge_requests` (the cluster and its MR) and `failed` (the cluster, the
problem `code` its write failed with, and the detail), both in pick order;
`docs/notes/2026-11-12-import-mr-per-cluster.md` has the JSON. When no MR
opened, the answer is the failure's problem, as for any other write: an
`AMBIGUOUS_WRITE` leads, because it is the one to check in GitLab before
importing again, else the first failure's; `details.problems` and
`details.failed` list every cluster. The web's result screen lists every
MR with its link and review page, and every failure with what it means.

## Alternatives rejected

- **One MR for the import** (ADR-0037): one review for many clusters is
  all or nothing, as above.
- **One at a time**: a full import can outlast the proxy, as above.
- **All at once**: fifty concurrent commits on one project, for a few
  seconds saved.
- **All or nothing across the MRs** (close the opened ones when one
  fails): closing is a write too, which can fail or go unconfirmed, and
  each MR standing on its own is the point.
- **Keep starting MRs after GitLab stops answering**: each would wait out
  the read timeout, and the request would outlast the proxy.
- **Retrying a failed MR**: a write is never retried (ADR-0006); the person
  imports that cluster again, after checking GitLab if the write was
  unconfirmed.

## Consequences

- An import of *n* clusters opens *n* MRs, each approved, merged or
  rejected on its own; a cluster follows the flavor once its own MR merges.
- An import can partly succeed. The result says which MRs opened; the
  others can be imported again. A cluster whose MR is open is still
  unlinked on main, so a second import opens a second MR for it, as
  before: once one merges the other conflicts in GitLab, which refuses to
  merge it.
- The web-visible answer of `POST /specs/{name}/import` changes
  (the API note above); the request and the preview do not.
- No metric changes: an import makes the same `commit` and
  `create_merge_request` calls, one pair per cluster, and
  `wingman_dependency_requests_total{outcome="ambiguous"}` still counts an
  unconfirmed one. Each MR that did not open is logged (`event`
  `import_mr_not_opened`).
- `ClusterProvisioner` is `apply` alone: a provisioner that starts a
  workflow (ADR-0017) has one method to implement.
- MRs opened before this change, titled `Import spec <flavor> into <n>
  clusters`, still parse: the title format is unchanged (ADR-0007).
- No other day1 write opens one MR for several clusters: create, modify,
  delete and sync take one cluster, a spec's MR changes only the specs
  repo, and editing an MR commits only files that MR already changes.

## Verification

- `apps/day1-service/tests/unit/application/test_imports.py`: one MR per
  cluster, each changing only its own file byte for byte with its own
  drift in the description; a cluster follows the flavor once its own MR
  merges; a refused or moved pick opens none; a file that moves before
  its commit fails only its MR; an unconfirmed write is reported, sent
  once, and starts no more; at most four open at once, results in pick
  order.
- `apps/day1-service/tests/unit/infrastructure/test_merge_requests.py`: an
  import's commit, title, branch, labels and footer; two imports in the
  same second get a branch each; a moved file commits nothing.
- `apps/day1-service/tests/unit/test_guards.py`: an import touches exactly
  the cluster file.
- `apps/day1-service/tests/api/test_flavor_links_api.py`: the 201 JSON, a
  partly failed import, and the problem when none opened.
- `apps/web/e2e/tests/flavor-import.spec.ts`: the result screen with every
  MR and every failure.
