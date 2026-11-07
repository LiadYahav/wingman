#!/usr/bin/env bash
# Start a local GitLab CE for development and the live contract suite.
#
#   scripts/dev/gitlab-up.sh          # start (or create) the container, wait until it serves
#   scripts/dev/gitlab-up.sh token    # also (re)create the local admin token
#
# GitLab needs ~4 GB of RAM: on macOS raise the podman VM first
# (`podman machine stop && podman machine set --memory 8192 && podman machine start`).
# The first start takes several minutes. Data lives in the wingman-gitlab-* volumes.
#
# The token below is for this local container only; never reuse it anywhere else.
set -euo pipefail

IMAGE="docker.io/gitlab/gitlab-ce:19.5.3-ce.0" # the version the contract suite was verified on (ADR-0005)
NAME="wingman-gitlab"
URL="http://localhost:8929"
TOKEN="wingman-local-dev-token-0001"
RUNTIME="$(command -v podman || command -v docker)"

if "$RUNTIME" ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "$NAME is running"
elif "$RUNTIME" ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  "$RUNTIME" start "$NAME" >/dev/null
else
  # puma/sidekiq/prometheus trimmed so it fits a laptop.
  "$RUNTIME" run -d --name "$NAME" --hostname gitlab.local \
    -p 8929:80 -p 8922:22 --shm-size=512m \
    -e GITLAB_OMNIBUS_CONFIG="external_url '$URL'; nginx['listen_port'] = 80; gitlab_rails['gitlab_shell_ssh_port'] = 8922; puma['worker_processes'] = 0; sidekiq['concurrency'] = 5; prometheus_monitoring['enable'] = false;" \
    -v wingman-gitlab-config:/etc/gitlab \
    -v wingman-gitlab-logs:/var/log/gitlab \
    -v wingman-gitlab-data:/var/opt/gitlab \
    "$IMAGE" >/dev/null
fi

# /-/health answers 404 to non-local callers by default; the sign-in page does not.
printf 'waiting for %s ' "$URL"
for _ in $(seq 1 120); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$URL/users/sign_in")" == 200 ]]; then
    echo " up"
    break
  fi
  printf '.'
  sleep 10
done

if [[ "${1:-}" == token ]]; then
  "$RUNTIME" exec "$NAME" gitlab-rails runner "
    u = User.find_by_username('root')
    t = u.personal_access_tokens.find_by(name: 'wingman-dev') ||
        u.personal_access_tokens.new(name: 'wingman-dev', scopes: ['api', 'admin_mode'], expires_at: 300.days.from_now)
    t.set_token('$TOKEN'); t.save!" >/dev/null
  echo "token ready"
fi

cat <<EOF

GITLAB_URL=$URL
GITLAB_TOKEN=$TOKEN

Seed the fixture repos:  uv run python scripts/dev/seed_gitlab.py
Live contract suite:     WINGMAN_TEST_GITLAB_URL=$URL WINGMAN_TEST_GITLAB_TOKEN=$TOKEN uv run pytest -m live_gitlab
EOF
