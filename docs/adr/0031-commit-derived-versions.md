# ADR-0031: Derive the version from Conventional Commits, as server-scan and herzi do

Date: 2026-11-07
Status: Proposed

For the user to decide. Nothing here is implemented; ADR-0030 is what runs.

## Context

ADR-0030 keeps the root `VERSION` file as the release input and guards it:
a release happens when someone bumps it, the version never moves backwards,
and a version tag is never re-pointed. server-scan (its ADR-0010) and herzi
instead compute the version on every push to main with
`PaulHatch/semantic-version` from the Conventional Commit subjects since the
last `v*` tag: `feat!:` or a `BREAKING CHANGE:` footer bumps major, `feat:`
minor, anything else patch. Both run the same forward-only guard and the same
release notes as ADR-0030 does.

## Decision (proposed)

- Retire `VERSION`. Seed the sequence by tagging the commit that carries the
  last `VERSION` release (for example `v3.0.0`), so the first computed version
  continues from it instead of starting at `0.0.1`.
- In the `release-plan` job, compute the next version with
  `PaulHatch/semantic-version@9f72830310d5ed81233b641ee59253644cd8a8fc # v6.0.2`
  (`tag_prefix: "v"`; the SHA server-scan pins, verified to resolve on
  2026-11-07), and feed it to the existing `scripts/release.py plan` in place
  of the file, so the guard, the API tag, `publish` and the release notes stay
  as they are.
- Every push to main is then a release: `v<X.Y.Z>`, `<short_sha>` and
  `latest`, as today.

## Trade-offs

For:

- No human step to forget, and no merge conflict on `VERSION` between
  branches; every main build has its own semver, so `wingman_build_info`
  and the image tags always say which release is running.
- The commit subjects already decide the release notes (ADR-0030); they would
  decide the number too, from the same text.
- One release model across the team's repositories.

Against:

- Every merge is a release, including ones that only change CI or docs
  (they bump patch). Releases stop marking "a version worth announcing";
  that meaning would move to the release notes.
- The bump is only as right as the commit subjects. A breaking change
  committed as `fix:` ships as a patch. Wingman's history mixes conventional
  and free-form subjects; free-form ones count as patch.
- PaulHatch counts patches per commit since the last version-changing commit,
  so one merge of three `fix:` commits advances the patch by three
  (server-scan ADR-0010 records the same).
- It adds a third-party action to the job that holds `contents: write`. It is
  SHA-pinned and checked by zizmor (ADR-0032), but it is one more pin to keep
  current, and server-scan has already had to replace one tagging action whose
  Node runtime GitHub removed.
- Merge commits ("Merge pull request #N") are commits too; they would count as
  patch unless the repository moves to squash merges with conventional PR
  titles.

## Alternatives

- **Keep ADR-0030** (VERSION bumps, guarded). Releases stay deliberate; the
  cost is the manual bump and its forgetting.
- **Compute only the patch**: keep major/minor in `VERSION` and append a
  commit count. Fewer surprises, but two sources of truth.

## Consequences (if accepted)

- Supersedes ADR-0030's "a release is cut by bumping VERSION"; the rest of
  ADR-0030 stays.
- CLAUDE.md's convention 2 gains a rule: a breaking change is `feat!:` or
  carries a `BREAKING CHANGE:` footer.

## Verification (when implemented)

`tests/repo/test_ci_scripts.py` keeps the guard's rules; a dry run of
`PaulHatch/semantic-version` on a fork with the seed tag shows the first
computed version continuing from it.
