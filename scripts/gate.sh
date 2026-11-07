#!/usr/bin/env bash
# The local CI gate: runs what .github/workflows/ci.yml runs, in the same
# order, and reports every failure instead of stopping at the first.
#
#   scripts/gate.sh          # everything
#   scripts/gate.sh python   # only the Python checks
#   scripts/gate.sh web      # only the web checks
#
# Keep this file and ci.yml in step: a check added to one belongs in both.
set -uo pipefail

cd "$(dirname "$0")/.."
scope="${1:-all}"
failed=()

step() {
  local name=$1
  shift
  printf '\n\033[1m== %s\033[0m\n' "$name"
  if "$@"; then
    printf '\033[32mok\033[0m %s\n' "$name"
  else
    printf '\033[31mFAILED\033[0m %s\n' "$name"
    failed+=("$name")
  fi
}

# New code is held to the strict bar; legacy packages keep their old lint
# until their rewrite (ADR-0001).
STRICT=(packages/wingman-core)
LEGACY=(packages/shared-python apps/day1-service apps/day2-service)

if [[ $scope == all || $scope == python ]]; then
  step "uv sync --locked" uv sync --locked --all-packages --all-groups --all-extras --quiet
  step "ruff check" uv run ruff check "${STRICT[@]}"
  step "ruff format --check" uv run ruff format --check "${STRICT[@]}"
  step "ty" uv run ty check "${STRICT[@]}"
  step "import-linter" uv run lint-imports
  step "pytest (coverage >= 90%)" uv run pytest --cov --cov-fail-under=90 -q
  step "pip-audit" uv run --with pip-audit==2.10.1 pip-audit --skip-editable --progress-spinner off
  step "deptry (wingman-core)" bash -c 'cd packages/wingman-core &&
    uv run --with deptry==0.24.0 deptry src --known-first-party wingman_core'
  step "legacy ruff" uv run ruff check "${LEGACY[@]}"
  step "legacy mypy" bash -c 'for d in packages/shared-python/src/wingman_shared apps/day1-service/src apps/day2-service/src; do uv run mypy "$d" --ignore-missing-imports || exit 1; done'
fi

if [[ $scope == all || $scope == web ]]; then
  step "npm ci" npm ci --no-audit --no-fund --silent
  step "web lint" npm run lint --workspace=web --silent
  step "web typecheck" bash -c 'cd apps/web && npx tsc --noEmit'
  step "web build" npm run build --workspace=web --silent
fi

if ((${#failed[@]})); then
  printf '\n\033[31m%d check(s) failed:\033[0m %s\n' "${#failed[@]}" "${failed[*]}"
  exit 1
fi
printf '\n\033[32mAll checks passed.\033[0m\n'
