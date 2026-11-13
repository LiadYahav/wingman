#!/usr/bin/env bash
# The local CI gate: runs what .github/workflows/ci.yml runs, in the same
# order, and reports every failure instead of stopping at the first.
#
#   scripts/gate.sh          # everything below, in this order
#   scripts/gate.sh ci       # workflows and scripts: actionlint, zizmor, shellcheck (pinned, scripts/ci-tools.sh)
#   scripts/gate.sh python   # only the Python checks, including the requirement-export drift check
#                            # and the file-size limits (of every language: ADR-0056)
#   scripts/gate.sh chart    # only the Helm chart and alert-rule checks (needs helm, promtool)
#   scripts/gate.sh web      # only the web checks, including npm audit
#   scripts/gate.sh e2e      # the mocked Playwright suite against a production build
#
# e2e needs Playwright's browser (`cd apps/web && npx playwright install chromium --only-shell`);
# PLAYWRIGHT_CHANNEL=chrome runs it on an installed Google Chrome instead. On macOS
# that Chrome can wake Google's updater, which inherits the browser's output: the
# run then waits forever after its last test (each browser's exit is never seen).
# `pkill -f GoogleUpdater.app` lets it finish. CI's headless shell has no updater.
# Not here: image builds (CI's `images` job; locally `podman build -f apps/web/Dockerfile .`)
# and the live GitLab contract suite (nightly in CI, .github/workflows/live-gitlab.yml).
#
# Keep this file and ci.yml in step: a check added to one belongs in both.
# Which Python packages get which checks lives in scripts/python-packages.sh.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
scope="${1:-all}"
failed=()

case $scope in
  all | ci | python | chart | web | e2e) ;;
  *)
    echo "usage: scripts/gate.sh [all|ci|python|chart|web|e2e]" >&2
    exit 2
    ;;
esac

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

# shellcheck source=scripts/python-packages.sh
source scripts/python-packages.sh

tools="${XDG_CACHE_HOME:-$HOME/.cache}/wingman/ci-tools"

zizmor_all() {
  # The online audits (impostor commits, a `# vX.Y.Z` comment that names
  # another tag) need a GitHub token. CI always has one; locally gh's is used.
  local token=${GH_TOKEN:-${GITHUB_TOKEN:-}}
  if [[ -z $token ]] && command -v gh >/dev/null; then
    token=$(gh auth token 2>/dev/null) || token=""
  fi
  if [[ -z $token ]]; then
    echo "no GitHub token (run gh auth login): offline audits only here; CI runs them all"
    "$tools/zizmor" --offline .github
  else
    GH_TOKEN=$token "$tools/zizmor" .github
  fi
}

deptry_all() {
  local entry
  for entry in "${DEPTRY[@]}"; do
    (cd "${entry%%:*}" && uv run --with deptry==0.24.0 deptry src --known-first-party "${entry#*:}") || return 1
  done
}

helm_template_all() {
  local values
  for values in deploy/helm/wingman/ci/*.yaml; do
    helm template wingman deploy/helm/wingman --namespace wingman -f "$values" >/dev/null || {
      echo "failed: $values"
      return 1
    }
  done
}

web_built=false

if [[ $scope == all || $scope == ci ]]; then
  step "install actionlint, zizmor, shellcheck (pinned, checksum-verified)" scripts/ci-tools.sh "$tools"
  step "actionlint" "$tools/actionlint" -shellcheck "$tools/shellcheck"
  step "zizmor" zizmor_all
  step "shellcheck (scripts)" "$tools/shellcheck" scripts/*.sh scripts/dev/*.sh
fi

if [[ $scope == all || $scope == python ]]; then
  step "uv sync --locked" uv sync --locked --all-packages --all-groups --all-extras --quiet
  step "requirement exports match uv.lock" scripts/export-requirements.sh --check
  step "file sizes (baseline may only shrink)" python3 scripts/check-file-size.py
  step "ruff check" uv run ruff check "${STRICT[@]}"
  step "ruff format --check" uv run ruff format --check "${STRICT[@]}"
  step "ty" uv run ty check "${STRICT[@]}"
  step "import-linter" uv run lint-imports
  step "pytest (coverage >= 90%)" uv run pytest --cov --cov-fail-under=90 -q
  step "pip-audit" uv run --with pip-audit==2.10.1 pip-audit --skip-editable --progress-spinner off
  step "deptry" deptry_all
fi

if [[ $scope == all || $scope == chart ]]; then
  step "helm lint --strict" helm lint --strict deploy/helm/wingman
  step "helm template (every deploy/helm/wingman/ci fixture)" helm_template_all
  step "promtool check rules" promtool check rules deploy/helm/wingman/files/alerts.rules.yaml
  step "promtool test rules" promtool test rules deploy/helm/wingman/tests/alerts.test.yaml
fi

if [[ $scope == all || $scope == web || $scope == e2e ]]; then
  step "npm ci" npm ci --no-audit --no-fund --silent
fi

if [[ $scope == all || $scope == web ]]; then
  step "npm audit (allowlist may only shrink)" python3 scripts/npm-audit.py
  step "web lint" npm run lint --workspace=web --silent
  step "web unit tests (vitest)" npm run test:unit --workspace=web --silent
  step "web typecheck" bash -c 'cd apps/web && npx tsc --noEmit'
  step "web build" npm run build --workspace=web --silent
  web_built=true
fi

if [[ $scope == all || $scope == e2e ]]; then
  $web_built || step "web build" npm run build --workspace=web --silent
  # CI=1 as in CI: the production server (`next start`), four workers, retries.
  step "playwright (mocked suite)" env CI=1 npm run test:e2e:mocked --workspace=web
fi

if ((${#failed[@]})); then
  printf '\n\033[31m%d check(s) failed:\033[0m %s\n' "${#failed[@]}" "${failed[*]}"
  exit 1
fi
printf '\n\033[32mAll checks passed.\033[0m\n'
