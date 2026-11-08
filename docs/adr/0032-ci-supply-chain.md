# ADR-0032: CI checks its own supply chain: zizmor-enforced SHA pins, checksum-verified tools, an npm audit that only shrinks

Date: 2026-11-07
Status: Accepted

## Context

CI's actions were SHA-pinned by hand (following server-scan ADR-0013), but
nothing checked that the next edit kept them pinned, that a `# vX.Y.Z`
comment named the tag its SHA came from, or that a job held only the
permissions it used. Every checkout left its token in `.git/config`. The
workflow files themselves were never linted. `npm audit` did not run at
all: on 2026-11-07 it reported 147 advisories in 37 packages, two of them
critical.

## Decision

- **A `workflows` job (and `scripts/gate.sh ci`) lints CI itself**: actionlint
  (with a pinned shellcheck for every `run:` block), zizmor, and shellcheck on
  `scripts/`. zizmor runs online in CI, so it also catches impostor commits
  and `# vX.Y.Z` comments that do not match the SHA; `.github/zizmor.yml`
  requires a hash pin for every action, first-party ones included (zizmor
  1.32's default, written out so a change of default cannot loosen it). The
  workflow is clean under zizmor's pedantic persona.
- **Least privilege everywhere**: `permissions: {}` at the workflow level,
  each job declares what it uses; every checkout has
  `persist-credentials: false`; the release tag is created through the API, so
  no checkout ever holds a write token; every job has a timeout; a newer push
  cancels a branch's run, never a main run.
- **Tools are downloaded pinned and checksum-verified**, as herzi does for
  helm and promtool: `scripts/ci-tools.sh` installs actionlint 1.7.12, zizmor
  1.32.0 and shellcheck 0.11.0 for CI and the gate alike, refusing any other
  bytes. Checksums come from the release's checksum file where it has one,
  else from GitHub's recorded asset digests.
- **`npm audit` blocks**, for every dependency and every severity (what
  server-scan gates), through `scripts/npm-audit.py`: an advisory not listed
  by GHSA id in `scripts/npm-audit-allowlist.txt` fails, and so does a listed
  one npm no longer reports, so the allowlist can only shrink. Each group of
  entries says what fixes it.
- `pip-audit` and `deptry` stay as they were. Still no Dependabot or
  Renovate (ADR-0003).

## Alternatives rejected

- **`npm audit --audit-level=critical`** (or `--omit=dev`). It fails today
  either way (critical advisories in `next`), and a level lets every new
  high-severity advisory through unseen.
- **Fix every advisory here.** 64 need `package.json` changes (`next` 16.4.5
  for 37, monaco-editor, the shadcn CLI); they change what the app runs and
  belong in a web change verified by hand. The in-range lockfile updates that
  changed no `package.json` were made (83 advisories cleared).
- **A separate pin-check script.** zizmor's `unpinned-uses` with a hash-pin
  policy is that check, plus the comment and impostor checks.

## Consequences

- A tool bump is a version and four checksums in `scripts/ci-tools.sh`; a new
  zizmor audit may flag existing YAML, which is read as the tool changing.
- The allowlist starts at 64 entries, including the `next` RCEs; bumping
  `next` to 16.4.5 is the first thing to do to the web app.
- The gate runs zizmor's online audits with `gh auth token` when there is one
  and says so when it falls back to offline.

## Verification

- 2026-11-07: `scripts/gate.sh ci` passes; zizmor reports no findings under
  the regular and pedantic personas. A scratch workflow with
  `actions/checkout@v7` (and, separately, `@v7.0.1`) and a SHA commented with
  the wrong version fails with `unpinned-uses` and `ref-version-mismatch`.
- `tests/repo/test_ci_scripts.py::TestNpmAudit` pins the allowlist rules;
  `python3 scripts/npm-audit.py` reports 64 advisories, every one allowlisted.
