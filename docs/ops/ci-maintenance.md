# Keeping CI current

A manual pass, roughly quarterly (moved here from CLAUDE.md on 2026-11-17).

Nothing updates itself and there is no Dependabot or Renovate (ADR-0003,
ADR-0032). The pass:

1. **Action pins.** Compare each `uses:` comment (`# vX.Y.Z`) with the
   action's latest release. Resolve the new tag to its commit before pinning,
   dereferencing annotated tags:
   `gh api repos/<o>/<r>/git/ref/tags/<tag>` (an `object.type` of `tag` means
   one more `gh api repos/<o>/<r>/git/tags/<sha> --jq .object.sha`). Never
   copy a SHA from a README; server-scan was broken twice by tags that do not
   exist. Then `scripts/gate.sh ci`: zizmor refuses a tag pin and a comment that
   names another tag. `PaulHatch/semantic-version`'s defaults are the
   versioning rule (convention 2, ADR-0031): before bumping it, check that its
   `action.yml` defaults (`major_pattern`, `minor_pattern`,
   `search_commit_body`, `bump_each_commit`) did not change.
2. **Downloaded tools.** `scripts/ci-tools.sh` (actionlint, zizmor,
   shellcheck), `scripts/install-helm.sh` and the promtool step in `ci.yml`:
   new version plus every checksum, from the release's checksum file or the
   API's asset digests (the script header has the command).
3. **Vulnerable or unused.** `scripts/gate.sh python web` runs `pip-audit`,
   `deptry` and the npm audit gate. Prefer deleting an unused dependency to
   bumping it. A fixed advisory leaves `scripts/npm-audit-allowlist.txt` in the
   same commit (the gate fails until it does).
4. **Runtime deprecations.** Actions declare a Node runtime; GitHub removes
   old ones (server-scan had to replace a tagging action for that).
5. **Base images.** `apps/web/Dockerfile` (and the service Dockerfiles) pin
   UBI 9.8 by tag and digest, and CPython by checksum; docs/ops/images.md has
   the commands to resolve a new digest and checksums. The chart's nginx
   (`image.nginx`, UBI `nginx-124`) too: docs/ops/images.md, "The nginx image".
6. **ty and ruff** are pinned exactly in the root dev group; a ty bump moves
   diagnostics (ADR-0008), so bump it in its own commit and read new errors as
   ty changing. **hatchling** (root `build` group) follows the members'
   build-system; after a bump, `uv lock && scripts/export-requirements.sh`.
7. **Runner image.** Every job runs on `ubuntu-24.04`, not `ubuntu-latest`:
   when `ubuntu-latest` moved to 26.04, Playwright had no browser build for it
   and the E2E job failed. Move all jobs together, after checking Playwright
   supports the new image.
8. **GitLab CE** for the live contract: `live-gitlab.yml` and
   `scripts/dev/gitlab-up.sh` together, then record the run in ADR-0005.
