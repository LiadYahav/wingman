# ADR-0003: Dependencies are pinned exactly, in one workspace lockfile

Date: 2026-11-07
Status: Accepted

## Context

Wingman had three `uv.lock` files (shared-python, day1, day2) that nothing
used: CI ran `uv sync` without `--locked`, and the Dockerfiles ran
`pip install` with open ranges (`fastapi>=0.115,<1`), so each image build
resolved fresh versions. A build on Monday and a build on Friday of the same
commit could ship different code. Production is air-gapped: packages come
from a mirror that carries specific versions, so an unpinned resolve can also
fail outright.

The root `.python-version` said 3.12 while every package required 3.13.

## Decision

- One uv workspace at the repository root, one `uv.lock`. Members:
  `packages/wingman-core`, `packages/shared-python` (legacy),
  `apps/day1-service`, `apps/day2-service`.
- Direct dependencies of new packages are pinned with `==` in their own
  `pyproject.toml`. Dev tools are pinned in the root `[dependency-groups]`.
- CI and the gate install with `uv sync --locked`, which fails if
  `pyproject.toml` and `uv.lock` disagree.
- Python is 3.13 everywhere (`.python-version`, `requires-python`, images).
- No Dependabot or Renovate. server-scan tried Dependabot and removed it: it
  edited generated files and bumped transitive pins. Updates are a deliberate,
  reviewed pass.

## Alternatives rejected

- **Ranges plus a lockfile.** That only works if every install uses the lock,
  which the Dockerfiles did not. Exact pins make the intended version readable
  in `pyproject.toml` itself.
- **A lockfile per package.** It let two services ship different versions of
  the same library and was never enforced.

## Consequences

- Upgrading anything is an explicit edit plus `uv lock`, reviewed as a diff.
- The images install from the lock as well (2026-11-07). The web image runs
  `npm ci` against the root `package-lock.json` from the repository root.
  `scripts/export-requirements.sh` writes hash-pinned per-service exports
  (`deploy/python/requirements-{day1,day2}.txt`) and the members' build
  backend (`requirements-build.txt`, from the root `build` group); the Python
  images install those with `--require-hashes --no-deps` and build the
  workspace members offline (the pattern is in `docs/ops/images.md`, and the
  two service Dockerfiles adopt it with their rewrite). A `pyproject.toml`
  change is therefore `uv lock` plus the export script, committed together.

## Verification

`uv sync --locked` in CI and in `scripts/gate.sh` fails on any drift between
the manifests and `uv.lock`; `scripts/export-requirements.sh --check` (CI and
the gate) fails on any drift between `uv.lock` and the exports.
