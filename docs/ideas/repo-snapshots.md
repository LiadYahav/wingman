# Read each repo once per commit

**Status:** proposed, 2026-11-08. Waits on one decision (at the end). When it
is built, it gets an ADR next to ADR-0002 and ADR-0011.

## The problem

Pages are slow on production-sized repos, and the cause is the number of
calls, not the HTTP library. The adapter is a thin async httpx client with
pooled connections; python-gitlab would be slower (synchronous, ADR-0002).
Each read is one REST call:

- **A tree is paged.** `list_tree` gets 100 entries per call, one page after
  another. A team repo of 3,000 entries is 30 calls in a row before any file
  is read.
- **Every file is a call.** Topology reads every hosted-cluster file in the
  day1 repo and every team's control files. The catalog reads each chart's
  deploy config, values and every OCP-version pin.
- **The cache forgets after 15 s** (day2; day1 after 30 s, ADR-0011), even
  when nothing changed. Most page views read everything again.

Measured on the local fixture (5 teams, a few charts), cold: `/api/day2/teams`
28 calls, `/api/day2/addons` 28, `/api/day2/lints` 14. The count grows with
every file and every 100 tree entries. Production's numbers are in its own
metrics:

```promql
# calls per second, and seconds per call, by GitLabPort method
sum by (operation) (rate(wingman_dependency_requests_total{dependency="gitlab"}[5m]))
sum by (operation) (rate(wingman_dependency_request_duration_seconds_sum{dependency="gitlab"}[5m]))
  / sum by (operation) (rate(wingman_dependency_request_duration_seconds_count{dependency="gitlab"}[5m]))
```

A second risk comes with size: the catalog starts every chart's reads at
once. The client allows 100 connections, and a request that waits more than
`GITLAB_CONNECT_TIMEOUT_SECONDS` (5 s) for one fails as GitLab unavailable. A
large catalog on a slow link can fail that way.

## How the others read

None of them reads file by file:

- ArgoCD clones the repo.
- The team's `render_chain.py` renders from a checkout.
- The architect's workflows (`kubevirt-workflows`, `workflow/shared/git_client.py`)
  run `git clone --depth 1` and read the files from disk.

## Proposal

Per repo:

1. Once per TTL, one call for the branch head:
   `GET /projects/:id/repository/branches/<branch>`.
2. **Head unchanged:** keep everything read at that commit. A commit's
   content never changes, so it needs no expiry.
3. **Head moved:** one `GET /projects/:id/repository/archive.tar.gz?sha=<head>`.
   Every file goes into memory, and the tree is its paths. A size cap applies
   per repo, and the least recently used repos are dropped first.
4. Files a form edits still come from `read_file`: the values a user changes
   need their `last_commit_id`, which the guarded write sends back
   (ADR-0006). That is a few files per page, not the whole repo.
5. Read every repo at startup, so the first visitor doesn't wait.

**What changes:**
- A page view costs one call per repo when nothing changed, and two when it
  did, whatever the repo's size.
- A page reads one commit per repo. Today, reads at `main` during a push can
  mix two commits.

**What doesn't:** writes, MRs and the guards.

**The cost:**
- Two port methods (branch head, archive), with the adapter, the fake, and
  contract tests on GitLab CE.
- The day1 and day2 repositories move onto them. Above them, only the edit
  forms change: they ask for the files they edit by name.

**GitLab's archive limit:** 5 archives per minute per project and user, and
only when the `archive_rate_limit` feature flag is on (off by default; read
from CE 19.5.3's source). Wingman asks for an archive only when a repo's head
moves. On a 429 it reads that repo file by file, as today.

## Alternatives

| Option | Why not first |
|---|---|
| `git clone` / fetch (dulwich or the git binary) | After the first clone it transfers the least, but it needs a git client in the image and a second way to authenticate |
| GraphQL `blobs(paths:)` | Batches the file reads, but the tree is still paged |
| `POST /repository/blobs/batch` | Behind a feature flag, and also 5 per minute |
| A longer TTL | Fewer calls, but pages up to a minute old; ADR-0011 caps the TTL at 60 s |

## Small fixes worth doing anyway

- **Keyset pagination** for `list_tree` (`pagination=keyset`). GitLab
  recommends it for large trees; it is still one call per page.
- **A cap on calls in flight** (e.g. 32 per service), so a big catalog queues
  in Wingman instead of timing out waiting for a pooled connection.

## Decision needed

Build snapshot reads (recommended), or only the two small fixes first.
