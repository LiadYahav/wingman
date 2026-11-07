#!/usr/bin/env bash
# Installs the pinned workflow and shell linters (actionlint, zizmor and
# ShellCheck) into a directory, verifying each download against the sha256
# recorded below, as herzi's CI does for helm and promtool. CI's `workflows`
# job and `scripts/gate.sh ci` both use it, so they run the same versions.
#
#   scripts/ci-tools.sh <dir>    # installs <dir>/{actionlint,zizmor,shellcheck}
#
# Re-running is cheap: a tool already at the pinned version is kept.
#
# Bumping a tool: change its version and all four checksums. Take them from the
# release's own checksum file where there is one (actionlint), otherwise from
# the asset digests GitHub records for the release:
#   gh api repos/zizmorcore/zizmor/releases/tags/v<version> --jq '.assets[] | "\(.name) \(.digest)"'
# then run `scripts/gate.sh ci` and read any new finding as the tool changing.
set -euo pipefail

ACTIONLINT_VERSION=1.7.12
ZIZMOR_VERSION=1.32.0
SHELLCHECK_VERSION=0.11.0

dir=${1:?usage: scripts/ci-tools.sh <install-dir>}

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)
    actionlint_os=linux_amd64 zizmor_target=x86_64-unknown-linux-gnu shellcheck_target=linux.x86_64
    actionlint_sha=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8
    zizmor_sha=bb110cc765eca9cd7efb2e284a956be5974c60027b0970f16397d86208a9957b
    shellcheck_sha=b7af85e41cc99489dcc21d66c6d5f3685138f06d34651e6d34b42ec6d54fe6f6
    ;;
  Linux-aarch64 | Linux-arm64)
    actionlint_os=linux_arm64 zizmor_target=aarch64-unknown-linux-gnu shellcheck_target=linux.aarch64
    actionlint_sha=325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6
    zizmor_sha=cb152b207f815116d7fa1c1ee4614f61578803351395052908095e79adfd9fd0
    shellcheck_sha=68a8133197a50beb8803f8d42f9908d1af1c5540d4bb05fdfca8c1fa47decefc
    ;;
  Darwin-arm64)
    actionlint_os=darwin_arm64 zizmor_target=aarch64-apple-darwin shellcheck_target=darwin.aarch64
    actionlint_sha=aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f
    zizmor_sha=6efed18c4539a663fd3c851a2be9533fd8456c4e646d9416206da059154a0d3c
    shellcheck_sha=339b930feb1ea764467013cc1f72d09cd6b869ebf1013296ba9055ab2ffbd26f
    ;;
  Darwin-x86_64)
    actionlint_os=darwin_amd64 zizmor_target=x86_64-apple-darwin shellcheck_target=darwin.x86_64
    actionlint_sha=5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644
    zizmor_sha=6983143c719ada6845a69cc4dd2bacc215f971662fecd8bbd2678388e5ce5969
    shellcheck_sha=c2c15e08df0e8fbc374c335b230a7ee958c313fa5714817a59aa59f1aa594f51
    ;;
  *)
    echo "ci-tools.sh: no pinned build for $(uname -s)-$(uname -m)" >&2
    exit 1
    ;;
esac

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

# fetch <url> <sha256> <file>: download, then refuse anything but the pinned bytes.
fetch() {
  curl -sSfL --retry 3 -o "$3" "$1"
  local actual
  actual=$(sha256 "$3")
  if [[ $actual != "$2" ]]; then
    echo "ci-tools.sh: checksum mismatch for $1: expected $2, got $actual" >&2
    exit 1
  fi
}

mkdir -p "$dir"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if [[ "$("$dir/actionlint" -version 2>/dev/null | head -1)" != "$ACTIONLINT_VERSION" ]]; then
  fetch "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_${actionlint_os}.tar.gz" \
    "$actionlint_sha" "$work/actionlint.tar.gz"
  tar -xzf "$work/actionlint.tar.gz" -C "$work" actionlint
  install -m 0755 "$work/actionlint" "$dir/actionlint"
fi

if [[ "$("$dir/zizmor" --version 2>/dev/null)" != "zizmor $ZIZMOR_VERSION" ]]; then
  fetch "https://github.com/zizmorcore/zizmor/releases/download/v${ZIZMOR_VERSION}/zizmor-${zizmor_target}.tar.gz" \
    "$zizmor_sha" "$work/zizmor.tar.gz"
  tar -xzf "$work/zizmor.tar.gz" -C "$work" zizmor
  install -m 0755 "$work/zizmor" "$dir/zizmor"
fi

if ! "$dir/shellcheck" --version 2>/dev/null | grep -qx "version: $SHELLCHECK_VERSION"; then
  fetch "https://github.com/koalaman/shellcheck/releases/download/v${SHELLCHECK_VERSION}/shellcheck-v${SHELLCHECK_VERSION}.${shellcheck_target}.tar.gz" \
    "$shellcheck_sha" "$work/shellcheck.tar.gz"
  tar -xzf "$work/shellcheck.tar.gz" -C "$work" "shellcheck-v${SHELLCHECK_VERSION}/shellcheck"
  install -m 0755 "$work/shellcheck-v${SHELLCHECK_VERSION}/shellcheck" "$dir/shellcheck"
fi

"$dir/actionlint" -version | head -1 | sed 's/^/actionlint /'
"$dir/zizmor" --version
"$dir/shellcheck" --version | sed -n 's/^version: /shellcheck /p'
