# ADR-0035: The day1, specs and team repos are read once per commit, from GitLab's archive

Date: 2026-11-08
Status: Accepted

## Context

Pages were slow on production-sized repos. Every file was one REST call,
every 100 tree entries another, page after page, and ADR-0011's cache forgot
them all after 15 s (day2) or 30 s (day1), even when nothing had changed. On
the local GitLab CE 19.5.3, with a team repo of 1,200 files and 100 more
clusters, the add-ons catalog took 9 s and 357 calls on every load. The page
outlived its own cache, so even a repeated load was a miss. The day1 cluster
list took 2.5 s and 116 calls each time the cache expired.

The HTTP library was not the cause (ADR-0002): any client makes the same
calls. The others don't read file by file: ArgoCD clones, the team's
`render_chain.py` renders a checkout, and the architect's workflows
(`kubevirt-workflows`, `workflow/shared/git_client.py`) run `git clone
--depth 1`. Proposed in `docs/ideas/repo-snapshots.md`; the user chose this
option.

## Decision

- `GitLabPort` gets `get_branch` (a branch's head commit) and `read_archive`
  (every file at a commit, from `/repository/archive.tar.gz?sha=`, held in
  memory, never written to disk).
- `RepoSnapshots` (`wingman_core.infrastructure.snapshots`) uses them:
  - **Head:** a project's branch head is checked once per TTL (ADR-0011's
    setting).
  - **Archive:** downloaded once per head commit and kept until the branch
    moves on, because a commit's files never change. Concurrent readers share
    one download.
  - **Memory:** one snapshot per project, 128 MiB held in all, least recently
    used dropped first; a pod has 512 MiB.
  - **Fallback:** a repository over 64 MiB, or one GitLab won't archive (its
    archive rate limit, any other refusal), is read file by file at the same
    commit, each file once, with a warning in the log.
- day1 (`CachedRepository`: the day1 and specs repos) and day2 (the team
  repos and its day1 index) read files and trees at the default branch
  through it. Reads at another ref, history, commits, merge requests and the
  chart repos stay call by call under ADR-0011.
- **A read's `last_commit_id` is the commit the repository was read at**, not
  the file's own last change. GitLab's write guard
  (`Files::BaseService#file_has_changed?`) compares the file's last change as
  of the given commit with its last change on the branch, so any commit the
  file was read at is a valid guard. ADR-0006's guarded writes work
  unchanged. Wingman code that checks staleness itself asks the same
  question (day1's `RepoReads.changed_since`, two history lookups, on writes
  only), never `expected != current`.
- Where a file's own last change is shown (day1's "changed by, at"), it comes
  from `RepoReads.last_change`: one history lookup per file and head commit.

## Alternatives rejected

- **`git clone` / fetch (dulwich or the git binary).** After the first clone
  it transfers the least, but it needs a git client in the image and a second
  way to authenticate. The archive is one HTTP call through the same adapter,
  token and metrics.
- **GraphQL `blobs(paths:)`.** Batches file reads, but the tree is still
  paged.
- **`POST /repository/blobs/batch`.** Behind a feature flag in CE 19.5.3, and
  limited to 5 calls a minute.
- **A longer TTL.** Fewer calls, but pages up to a minute old; ADR-0011 caps
  the TTL at 60 s, and the catalog's own load time already outlasted 15 s.

## Consequences

- **Speed.** On the scaled local data:
  - the catalog takes 0.65 s with 20 calls on the first load, 0.03 s with
    none from cache, and 0.46 s with 14 after the TTL;
  - the day1 cluster list takes 0.09 s with 2 calls after the TTL;
  - every response is identical to the old code's, apart from
    `last_commit_id`.
- **Day1's first load after each merge** still costs one history lookup per
  cluster (2.3 s here), for "changed by, at". Carrying unchanged files'
  history forward from a compare would remove that; not done yet.
- **Rate limit.** GitLab limits archives to 5 a minute per project and user,
  only when its `archive_rate_limit` feature flag is on (off by default).
  Wingman asks only when a head moves; past the limit it reads file by file.
- **Consistency.** A page reads one commit per repository, never a mix of
  two.
- **Unknown guards.** GitLab accepts an unknown commit as a guard (pinned in
  the contract suite), so a client that sends a made-up `last_commit_id`
  bypasses GitLab's check. Day1's own check refuses it; day2 relies on GitLab
  alone, as before.
- **New metrics.** `get_branch` and `read_archive` are new `operation` label
  values (ADR-0010).

## Verification

- **Contract suite** (`wingman_core.testing.gitlab_contract`), on the fake and
  on GitLab CE 19.5.3:
  - `get_branch`, the archive at a commit, and the archive size cap;
  - any commit a file was read at guards its update;
  - an unknown commit lets the write through.
- **`tests/unit/infrastructure/test_snapshots.py`:**
  - one head check per TTL, a new archive only when the head moves;
  - one shared download;
  - the file-by-file fallback and the memory budget;
  - non-UTF-8 files refused.
- **day2** `test_each_repo_is_read_once_per_commit`: no calls within the TTL,
  then one head check per repo.
- **day1:**
  - `test_repositories.py`: after the TTL only the head is checked, and
    `changed_since` matches GitLab's guard;
  - `test_clusters.py`: an edit read before other files changed is not
    stale, and a cluster shows its own last change.
