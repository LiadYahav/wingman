# ADR-0032: CI checks its own supply chain: zizmor-enforced SHA pins, checksum-verified tools, an npm audit that only shrinks

Date: 2026-11-07
Status: Accepted; amended 2026-11-13 (the mocked E2E suite runs on two runners of four workers; a flaky test is annotated and its trace kept)

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

## Amendment (2026-11-13): the mocked E2E suite runs on two runners of four workers, and a flaky test shows

Measured on the 20 CI runs of 2026-11-12/13: a run took 8.5-11.6 minutes,
and the mocked Playwright job was its whole critical path, 8-10 minutes, of
which 484-538 s was the suite: 403 tests on one worker. One worker was
Playwright's scaffold default (the config's first commit), never a decision.
server-scan runs one because its E2E shares a live database; Wingman's
mocked tests share nothing (each page intercepts its own API calls, and
`next start` keeps no state). The next-longest job, Python, took 2.3-3.9
minutes (pytest, 2,724 tests in 122-164 s); main adds 1.3-1.7 minutes after
the checks (tag, publish, notes). The supply-chain rules above are unchanged.

- Under CI the suite runs **four workers**, one per vCPU of a public
  repository's runner, as server-scan's `pytest -n 4`. `scripts/gate.sh e2e`
  sets `CI=1`, so it runs the same way.
- **Retries stay at two**, so one flaky test cannot fail a run (4 of the 40
  runs before this had one, each passing on its retry). It still shows: the
  list reporter's summary names it, and on GitHub Playwright's `github`
  reporter puts it on the run as an annotation.
- **Two runners**: CI splits the suite with `--shard`, a matrix of two, four
  workers each; Playwright splits by test (fullyParallel), so the halves are
  even. Four workers are not four times one: locally half the suite took
  1.1-1.7 minutes on four against 2.6 on one, so on one runner the suite
  would still be the longest check. Each shard pays about 45 s of setup
  (checkout, `npm ci`, build). The gate runs the suite whole.
- Each shard uploads its HTML report **on failure, and when a test passed
  only on a retry**: that retry's trace (`trace: on-first-retry`) is the only
  `.zip` a report holds, so a flaky test can be debugged, not only seen.

Rejected:

- **One build shared by the Web and E2E jobs**: it saves about 16 s and makes
  E2E wait for Web (1.5-2 minutes).
- **Caching `.next/cache`**: the Turbopack build compiles in about 8 s.
- **pytest-xdist** for the Python job, the critical path once E2E is fast:
  locally `-n 4` took 26 s against 106 s, but coverage under xdist trips
  `filterwarnings = error` (a `module-not-measured` CoverageWarning crashes a
  worker). A new dependency and a change to the Python stage: its own unit
  of work.
- **A faster publish without the SBOM or the provenance**: they are the point
  of ADR-0030's publish.
