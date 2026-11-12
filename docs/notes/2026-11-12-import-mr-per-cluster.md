# Importing clusters into a flavor: one MR per cluster (2026-11-12)

Importing existing clusters into a flavor opened one day1 merge request for
every picked cluster (ADR-0037). It now opens one per cluster, so each
cluster's link is reviewed, merged or rejected on its own (ADR-0044, the
architect's decision, confirmed by the user). This note is the web-visible
change: the answer of `POST /api/day1/specs/{name}/import`. It replaces
the import part of `2026-11-08-flavors-v2-api-changes.md` §11; the preview
(`POST /specs/{name}/import/preview`) and the request do not change.

## 1. The request: unchanged

```json
{"spec_version": "1.0.0", "clusters": [{"name": "...", "site": "...", "mce": "...", "last_commit_id": "<from the preview>", "relink": false}]}
```

At most 50 clusters, each as the preview returned it.

## 2. Checked first, all together: unchanged

Every pick is checked before any MR opens, and one failing check opens
none:

- `422 VALIDATION_ERROR`: a `refused` or `linked` cluster, or a `relink`
  one without `relink: true`; one problem per cluster in
  `details.problems`, each starting with the cluster's name.
- `409 REVISION_CONFLICT`: a picked file changed since the preview's
  `last_commit_id`, or the flavor is no longer `spec_version`. Preview
  again. Another file changing does not make the import stale.

## 3. Then one MR per cluster: the answer changes

**Before:** `201`, one MR (the `MRDetail` other writes return), titled
`[Wingman/Day1] Import spec <flavor> into <n> clusters`.

**Now:** `201` when at least one MR opened:

```json
{
  "spec_name": "agent-baseline",
  "spec_version": "1.0.0",
  "merge_requests": [
    {
      "name": "ocp4-prod-lark-site1", "site": "site1", "mce": "ocp4-prod-mce-site1-a",
      "path": "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-lark-site1.yaml",
      "merge_request": {
        "iid": 21, "project_id": 1, "repo": "day1",
        "title": "[Wingman/Day1] Import cluster ocp4-prod-lark-site1 into spec agent-baseline v1.0.0",
        "web_url": "...", "source_branch": "platform/alice/import-cluster-ocp4-prod-lark-site1-20261112T101500",
        "labels": ["day1", "import", "wingman"], "sha": "...", "...": "the MRDetail other writes return"
      }
    }
  ],
  "failed": [
    {
      "name": "ocp4-prod-heron-site1", "site": "site1", "mce": "ocp4-prod-mce-site1-a",
      "path": "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-heron-site1.yaml",
      "code": "AMBIGUOUS_WRITE",
      "detail": "..."
    }
  ]
}
```

- `merge_requests` and `failed` are each in pick order; together they hold
  every picked cluster once.
- Each MR changes only its cluster's file: the header (`# specName`,
  `# specVersion`), nothing else. Its description is about that cluster
  only: its site and MCE, and what will show as its drift once it merges.
- `failed[].code` is the problem code the cluster's write failed with
  (ADR-0004):
  - `AMBIGUOUS_WRITE`: GitLab did not confirm it, so the MR may exist.
    Wingman never retries it (ADR-0006); check GitLab before importing
    that cluster again.
  - `GIT_UNAVAILABLE`: nothing was sent. Either GitLab could not be
    reached, or GitLab did not answer for an earlier cluster and no more
    MRs were started (the `detail` says
    `not sent: GitLab did not answer for <cluster>, ...`).
  - `REVISION_CONFLICT`: the file moved between the check and its commit.
  - Any other Git code (`GIT_PERMISSION_DENIED`, `GIT_REJECTED`,
    `ALREADY_EXISTS`, ...): GitLab refused that write.
- A cluster follows the flavor once its own MR merges. Importing the
  `failed` ones again (preview first) opens their MRs; a cluster whose MR
  is open is still `ready` in the preview, so importing it again opens a
  second MR.

**When no MR opened,** the answer is a problem, as for any other write: the
status and `code` of an `AMBIGUOUS_WRITE` if one cluster had it, else of
the first failure. With one cluster its `detail` is
`<cluster>: <what GitLab said>`; with several it is `GitLab confirmed none
of the <n> import merge requests`. `details.problems` lists
`<cluster>: <detail>` for each, and `details.failed` has each entry of
`failed` above.

## 4. What the web shows

The import sheet's third step lists every MR opened, with its title, a
link to its review page and to GitLab, and every cluster whose MR did not
open with what its code means (an unconfirmed write says to check GitLab
before trying again). The toast after an import is gone: the step is the
result.
