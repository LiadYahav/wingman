# shellcheck shell=bash
# Which Python packages get which checks. Sourced by scripts/gate.sh and by
# the `python` job in .github/workflows/ci.yml, so the two cannot disagree.
# When a package is rewritten onto wingman-core (ADR-0001), move it from the
# LEGACY lists to STRICT and DEPTRY here, and nowhere else.
# shellcheck disable=SC2034  # the arrays are read by the scripts that source this file

# ruff check, ruff format --check and ty.
STRICT=(packages/wingman-core apps/day1-service tests/repo scripts/release.py scripts/npm-audit.py scripts/assert-junit.py)

# deptry, per package, run from the package directory: "<dir>:<first-party import name>".
DEPTRY=(packages/wingman-core:wingman_core apps/day1-service:wingman_day1)

# The legacy packages keep their old lint until they are rewritten. They have
# no tests yet; none are faked here.
LEGACY=(packages/shared-python apps/day2-service)
LEGACY_MYPY=(packages/shared-python/src/wingman_shared apps/day2-service/src)
