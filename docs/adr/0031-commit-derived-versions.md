# ADR-0031: Every merge to main is a release whose version comes from Conventional Commits, as in server-scan

Date: 2026-11-07 (proposed); 2026-11-08 (accepted)
Status: Accepted (user decision 2026-11-08; supersedes in part ADR-0030)

## Context

ADR-0030 kept the root `VERSION` file as the release input and guarded it:
a release happened when someone bumped it, the version never moved backwards,
and a version tag was never re-pointed. Between releases, main published only
`<short_sha>` and `latest`, so most deployed images had no version at all.
server-scan (its ADR-0010) and herzi instead compute the version on every
push to main with `PaulHatch/semantic-version` from the Conventional Commit
subjects since the last `v*` tag, and run the same forward-only guard and the
same release notes as ADR-0030 does.

The user, 2026-11-08: "I am thinking the sha image tag concept is stupid; I
want a release version number as server-scan."

## Decision

- **`VERSION` is retired.** The sequence continues from `v3.0.0`, the last
  release cut by `VERSION` (PR #17, under ADR-0030): the first computed
  version is `3.0.1` or above, never `0.0.1`.
- **Every push to main is a release.** The `release-plan` job computes the
  version with `PaulHatch/semantic-version@9f72830310d5ed81233b641ee59253644cd8a8fc # v6.0.2`
  and `tag_prefix: "v"` (the only input server-scan sets), on a checkout with
  `fetch-depth: 0` (full history and every tag). It passes the result to
  `scripts/release.py plan --version`, which refuses a malformed version, one
  below any `v*` git tag or published image version, one whose git tag is on
  another commit, and one already in the registry without a git tag. The one
  exception is the tag already on this very commit: a re-run (the action
  returns a tagged commit's own version). On a pull request the same job
  computes the version its merge would release, so a bad one fails first.
- **The rest of ADR-0030 stays:** `release-tag` creates the annotated
  `v<X.Y.Z>` tag through the API, `publish` pushes each image with an SBOM,
  BuildKit provenance and a signed SLSA attestation, and `release-notes`
  writes the GitHub release from the subjects since the previous tag. Pull
  requests build every image without pushing.
- **Image tags are server-scan's set:** `X.Y.Z` (never moves), `X.Y` and `X`
  (rolling), `latest`, and `sha-<short sha>`; the version tag has no `v`
  (`3.0.1`, not `v3.0.1`). The git tag and GitHub release keep it (`v3.0.1`).
  `WINGMAN_VERSION` and the `org.opencontainers.image.version` label are
  `X.Y.Z`. Deploy an `X.Y.Z` (docs/ops/images.md).
- **The subjects decide the bump**, with the action's defaults (read from its
  source at that SHA): a `!` before the colon (`feat!:`, `fix(day1)!:`) or
  `BREAKING CHANGE:` in a **subject** is major; `feat:` or `feat(<scope>):`
  is minor; anything else, including merge commits and free-form subjects, is
  patch. Bodies are not searched (`search_commit_body` is off), so a
  `BREAKING CHANGE:` footer alone does not bump the major. One release bumps
  by one (`bump_each_commit` is off): a merge of three `fix:` commits is one
  patch, not three. CLAUDE.md convention 2 says how to ask for a bump.

## Trade-offs

For:

- No human step to forget and no merge conflict on `VERSION`; every main
  build has its own version, so `wingman_build_info` and the image tags
  always say which release runs.
- The commit subjects already decided the release notes; they decide the
  number too, from the same text.
- One release model across the team's repositories.

Against:

- Every merge is a release, including CI- or docs-only ones (patch).
  "A version worth announcing" moves to the release notes.
- The bump is only as right as the subjects. A breaking change committed as
  `fix:` ships as a patch.
- A third-party action runs in a job that reads the repository; it holds no
  write permission (`release-tag` writes, through the API) and is SHA-pinned
  and checked by zizmor (ADR-0032), but it is one more pin to keep current.

## Alternatives rejected

- **Keep ADR-0030** (VERSION bumps, guarded): the manual bump is forgotten,
  and between bumps images are named only by a sha.
- **Compute only the patch** (major/minor in `VERSION`, a commit count
  appended): two sources of truth.

## Consequences

- Supersedes ADR-0030's "a release is cut by bumping VERSION" and its tag set
  (`<short_sha>`, `latest`, `v<VERSION>`). Images published before this as
  `v3.0.0` or `<short_sha>` stay where they are; the guard counts a `v3.0.0`
  image tag as a release, so no version is ever published twice.
- A main run that fails a check creates no tag; the next merge computes the
  same version on its own commit. A run that fails after tagging is finished
  by re-running it (ADR-0030); the next merge releases the next version.
- Main runs never overlap (the workflow's concurrency group), so two merges
  never compute the same version.

## Verification

- `tests/repo/test_ci_scripts.py::TestReleasePlan` pins the guard,
  `::TestReleaseNotes` the notes and their `X.Y.Z` image lines, and
  `::TestPublishedTags` the image tag set in `ci.yml`.
- 2026-11-08: the action's defaults (`major_pattern` `/!:|BREAKING CHANGE:/`,
  `minor_pattern` `/feat(\(.+\))?:/`, subjects only, one bump per release,
  a tagged commit keeps its version) read from its `action.yml` and
  `DefaultVersionClassifier.ts` at `9f72830`; `v6.0.2` dereferences to that
  commit. actionlint and zizmor (pedantic) pass. The first computed release,
  `v3.0.1`, can only run on GitHub, after `v3.0.0`.
