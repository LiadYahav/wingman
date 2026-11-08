#!/usr/bin/env bash
# Installs the pinned helm (linux-amd64, CI's runners) into /usr/local/bin,
# verifying the download against the checksum helm publishes, as herzi's CI
# does. CI's `chart` job needs it for lint and template, the `python` job for
# day2's oracle test, which renders the platform charts as render_chain.py does.
#
#   scripts/install-helm.sh
#
# Bumping helm: change the version and the checksum, taken from
# https://get.helm.sh/helm-v<version>-linux-amd64.tar.gz.sha256sum
set -euo pipefail

HELM_VERSION=4.3.1
HELM_SHA256=0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -sSfL --retry 5 --retry-delay 5 -o "$work/helm.tar.gz" "https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz"
echo "${HELM_SHA256}  $work/helm.tar.gz" | sha256sum --check --strict
tar -xzf "$work/helm.tar.gz" -C "$work" linux-amd64/helm
sudo install -m 0755 "$work/linux-amd64/helm" /usr/local/bin/helm
helm version --short
