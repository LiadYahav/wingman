# shellcheck shell=bash
# Which Python packages get which checks. Sourced by scripts/gate.sh and by
# the `python` job in .github/workflows/ci.yml, so the two cannot disagree.
# A new package or script goes in STRICT (and a package in DEPTRY) here, and
# nowhere else.
# shellcheck disable=SC2034  # the arrays are read by the scripts that source this file

# ruff check, ruff format --check and ty.
STRICT=(packages/wingman-core apps/day1-service apps/day2-service tests/repo scripts/release.py scripts/npm-audit.py scripts/assert-junit.py scripts/check-file-size.py scripts/dev)

# deptry, per package, run from the package directory: "<dir>:<first-party import name>".
DEPTRY=(packages/wingman-core:wingman_core apps/day1-service:wingman_day1 apps/day2-service:wingman_day2)
