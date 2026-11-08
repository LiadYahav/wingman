#!/usr/bin/env bash
# Writes the hash-pinned requirement exports the Python images install from
# (ADR-0003, docs/ops/images.md), and checks them.
#
#   scripts/export-requirements.sh           # regenerate deploy/python/requirements-*.txt
#   scripts/export-requirements.sh --check   # fail if a committed export differs from uv.lock
#
# requirements-<service>.txt is what uv.lock resolves for one service: its
# runtime dependencies, each with --hash lines, no dev dependencies and no
# workspace members (wingman-core, the service itself), which
# the image builds from this checkout. requirements-build.txt is the root
# `build` group: the build backend those members need, so the image builds
# their wheels with no index at all.
#
# They are generated files: never edit one by hand. Change a pyproject.toml,
# run `uv lock`, then this script. CI and scripts/gate.sh run --check, so an
# export cannot drift from the lock.
set -euo pipefail
cd "$(dirname "$0")/.."

# "<service>:<directory>"; the uv package name is read from its pyproject.toml.
SERVICES=(day1:apps/day1-service day2:apps/day2-service)
OUT_DIR=deploy/python

check=false
case "${1:-}" in
  "") ;;
  --check) check=true ;;
  *)
    echo "usage: scripts/export-requirements.sh [--check]" >&2
    exit 2
    ;;
esac

package_name() {
  python3 -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["name"])' "$1/pyproject.toml"
}

# Exported to stdout, not with -o, so uv's header names the same command in
# every checkout and --check compares like with like.
uv_export() {
  uv export --locked --no-emit-workspace --format requirements-txt --quiet "$@"
}

drifted=()

# write_or_check <target> <content>
write_or_check() {
  if $check; then
    if ! diff -u --label "$1 (committed)" --label "$1 (from uv.lock)" "$1" - <<<"$2"; then
      drifted+=("$1")
    fi
  else
    printf '%s\n' "$2" >"$1"
    echo "wrote $1 ($(grep -c -- '--hash=' "$1") hashes)"
  fi
}

mkdir -p "$OUT_DIR"
for entry in "${SERVICES[@]}"; do
  service=${entry%%:*}
  package=$(package_name "${entry#*:}")
  write_or_check "$OUT_DIR/requirements-$service.txt" "$(uv_export --package "$package" --no-dev)"
done
write_or_check "$OUT_DIR/requirements-build.txt" "$(uv_export --only-group build)"

if ((${#drifted[@]})); then
  echo "out of date with uv.lock: ${drifted[*]}; run scripts/export-requirements.sh and commit the result" >&2
  exit 1
fi
if $check; then
  echo "requirement exports match uv.lock"
fi
