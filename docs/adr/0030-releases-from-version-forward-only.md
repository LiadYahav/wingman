# ADR-0030: A release is a VERSION bump that only moves forward; images build on every PR and publish from main

Date: 2026-11-07
Status: Accepted

## Context

CI pushed `ghcr.io/<owner>/wingman-{day1,day2,web}` on every merge to main
with three tags: `<short_sha>`, `latest` and `v<VERSION>`, where `VERSION` is
the root file a human edits. Nothing checked `VERSION`: every merge that did
not edit it re-pushed `v<VERSION>` over the previous image, so a version tag
named different code on different days, and a `VERSION` edited downwards
would have published an older number over newer code. No git tag or release
recorded what a version contained. Images were built only after the checks,
and a pull request never built them, so a broken Dockerfile surfaced on main.

server-scan and herzi compute the version from Conventional Commits and guard
it (server-scan ADR-0010): a tag is created once, never re-pointed, and never
lower than the last one; release notes come from commit subjects. Wingman
keeps `VERSION` for now (ADR-0031 proposes the switch), so the same guarantees
are applied to it.

## Decision

- **A release is cut by bumping `VERSION`** to an `X.Y.Z` that no release
  has used. `scripts/release.py plan` (the `release-plan` job) compares it with
  every `v*` git tag and, on main, with the image tags already in ghcr:
  - new and above every existing version: this commit is the release;
  - already released on another commit: no release; the commit publishes
    `<short_sha>` and `latest` only, and `v<VERSION>` is never re-pointed;
  - its tag on this very commit: a re-run, every step repeats idempotently;
  - malformed, or below the newest release: the job fails, on the pull
    request as well, before it merges.
- **Main publishes in order:** `release-tag` creates the annotated
  `v<VERSION>` tag through the API; `publish` pushes each image with
  `docker/metadata-action` tags and OCI labels, an SBOM and BuildKit
  provenance, and a signed SLSA provenance attestation (`actions/attest`);
  `release-notes` creates the GitHub release from the Conventional Commit
  subjects since the previous tag (no CHANGELOG, as in server-scan and
  herzi). `publish` needs every check job.
- **Every pull request builds every image** (the `images` job, never
  pushing), in parallel with the checks; on main the same job fills the
  build cache `publish` pushes from.
- The tag set stays `<short_sha>`, `latest`, `v<VERSION>`; `latest` is never
  what a deployment should name (docs/ops/images.md).

## Alternatives rejected

- **Keep re-pushing `v<VERSION>` on every merge.** That is the bug: a version
  must name one build.
- **Fail main when `VERSION` was not bumped.** Most merges are not releases;
  they still publish `<short_sha>` images, as before.
- **Tag after pushing images.** A re-run after a failed tag step would find
  `v<VERSION>` in the registry without a git tag and could not tell its own
  image from an old one. Tagging first makes the git tag the record.

## Consequences

- A release that fails part-way is finished by re-running that run, not by a
  later commit (which sees the tag on another commit and releases nothing).
- Images that the old CI pushed as `v<VERSION>` without a git tag count as
  released: their version is never overwritten.
- GHCR answers 403 both for a missing package and for one the token cannot
  read; both count as "no tags", because a token that cannot read a package
  cannot push to it, so `publish` fails loudly instead.
- Artifact attestations need a public repository (or GitHub Enterprise
  Cloud); storage records need an organisation-owned one and are off.

## Verification

- `tests/repo/test_ci_scripts.py::TestReleasePlan` and `::TestReleaseNotes`
  pin every rule above.
- 2026-11-07, locally: `release.py plan` on this repository (no tags) plans
  `v1.0.0` as the first release; `release.py notes` renders the history;
  `release.py registry-tags` paged through 8608 tags of a public ghcr image
  and counted a missing one as none. The `release-tag`, `publish` and
  `release-notes` jobs can only run on GitHub; actionlint and zizmor
  (pedantic) pass on the workflow.
