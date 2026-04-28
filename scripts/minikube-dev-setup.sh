#!/usr/bin/env bash
# Full minikube dev setup for Wingman.
# Run once to get a working local environment.
#
# Prerequisites:
#   brew install minikube helm kubectl docker python3
#   python-gitlab is installed automatically (via venv) if missing
#
# Usage:
#   ./scripts/minikube-dev-setup.sh [--skip-gitlab] [--skip-seed] [--skip-build]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SKIP_GITLAB=false
SKIP_SEED=false
SKIP_BUILD=false
GITLAB_TOKEN=""

for arg in "$@"; do
  case $arg in
    --skip-gitlab) SKIP_GITLAB=true ;;
    --skip-seed)   SKIP_SEED=true ;;
    --skip-build)  SKIP_BUILD=true ;;
    --token=*)     GITLAB_TOKEN="${arg#--token=}" ;;
  esac
done

# ── Colors ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}==>${NC} $*"; }
warn()    { echo -e "${YELLOW}WARN:${NC} $*"; }
error()   { echo -e "${RED}ERROR:${NC} $*"; exit 1; }

# ── Check prerequisites ────────────────────────────────────────────────────────
info "Checking prerequisites..."
for cmd in minikube helm kubectl docker python3; do
  command -v "$cmd" >/dev/null 2>&1 || error "$cmd is required but not installed"
done

# Always use an isolated venv for the seed script — avoids externally-managed-environment errors
if [ ! -f "$REPO_ROOT/.venv-seed/bin/python3" ]; then
  info "Creating seed venv..."
  python3 -m venv "$REPO_ROOT/.venv-seed"
  "$REPO_ROOT/.venv-seed/bin/pip" install --quiet python-gitlab
fi
PYTHON="$REPO_ROOT/.venv-seed/bin/python3"

# ── Start minikube ─────────────────────────────────────────────────────────────
info "Starting minikube (4 CPUs, 6GB RAM)..."
if ! minikube status --format='{{.Host}}' 2>/dev/null | grep -q "Running"; then
  minikube start \
    --cpus=4 \
    --memory=6144 \
    --driver=docker \
    --addons=ingress
else
  info "minikube already running"
  minikube addons enable ingress 2>/dev/null || true
fi

MINIKUBE_IP=$(minikube ip)
info "minikube IP: ${MINIKUBE_IP}"

# ── Start GitLab CE on host ────────────────────────────────────────────────────
if [ "$SKIP_GITLAB" = false ]; then
  info "Starting GitLab CE container on host (port 8929)..."
  info "This may take 3-5 minutes on first run (large image)."

  # Check Docker memory — GitLab needs at least 4 GB
  DOCKER_MEM_BYTES=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  DOCKER_MEM_GB=$(( DOCKER_MEM_BYTES / 1024 / 1024 / 1024 ))
  if [ "$DOCKER_MEM_GB" -lt 4 ]; then
    warn "Docker only has ${DOCKER_MEM_GB}GB RAM available."
    warn "GitLab CE needs at least 4GB. Open Docker Desktop → Settings → Resources and increase memory."
    warn "Continuing anyway, but startup may be very slow or fail."
  else
    info "Docker memory: ${DOCKER_MEM_GB}GB (OK)"
  fi

  if docker ps --format '{{.Names}}' | grep -q "^wingman-gitlab$"; then
    info "GitLab container already running"
  elif docker ps -a --format '{{.Names}}' | grep -q "^wingman-gitlab$"; then
    info "Starting existing GitLab container..."
    docker start wingman-gitlab
  else
    info "Pulling and starting GitLab CE (first pull may take a few minutes)..."
    # external_url sets the URL GitLab uses in links.
    # nginx['listen_port'] = 80 forces nginx to listen on port 80 inside the
    # container regardless of the port in external_url — this is what Docker
    # maps (-p 8929:80). Without this, GitLab would try to listen on 8929
    # inside the container and nothing would be on port 80.
    docker run -d \
      --name wingman-gitlab \
      --hostname gitlab.local \
      -p 8929:80 \
      -p 8922:22 \
      -e GITLAB_OMNIBUS_CONFIG="external_url 'http://localhost:8929'; nginx['listen_port'] = 80; gitlab_rails['gitlab_shell_ssh_port'] = 8922;" \
      -v wingman-gitlab-config:/etc/gitlab \
      -v wingman-gitlab-logs:/var/log/gitlab \
      -v wingman-gitlab-data:/var/opt/gitlab \
      --shm-size=512m \
      gitlab/gitlab-ce:latest
  fi

  info "Waiting for GitLab to initialize (up to 15 minutes on first run)..."
  WAIT_SECS=0
  MAX_WAIT=900   # 15 minutes hard limit
  LAST_LOG_AT=0

  while true; do
    # Bail if container stopped/crashed
    CONTAINER_STATE=$(docker inspect --format='{{.State.Status}}' wingman-gitlab 2>/dev/null || echo "missing")
    if [ "$CONTAINER_STATE" != "running" ]; then
      echo ""
      error "GitLab container is not running (state: ${CONTAINER_STATE}). Check logs: docker logs wingman-gitlab"
    fi

    # Check if the web UI responds
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8929/-/health 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
      echo ""
      info "GitLab is up! (${WAIT_SECS}s)"
      break
    fi

    # Hard timeout
    if [ "$WAIT_SECS" -ge "$MAX_WAIT" ]; then
      echo ""
      error "GitLab did not start within ${MAX_WAIT}s. Last HTTP code: ${HTTP_CODE}. Run: docker logs wingman-gitlab 2>&1 | tail -30"
    fi

    # Print last log lines every 60 seconds so user can see progress
    if [ $(( WAIT_SECS - LAST_LOG_AT )) -ge 60 ]; then
      echo ""
      echo "  [${WAIT_SECS}s] HTTP ${HTTP_CODE} — still starting. Recent log:"
      docker logs wingman-gitlab 2>&1 | grep -E "(gitlab|error|warn|reconfigure|supervisord)" | tail -5 | sed 's/^/    /'
      echo ""
      LAST_LOG_AT=$WAIT_SECS
    else
      printf "."
    fi

    sleep 10
    WAIT_SECS=$(( WAIT_SECS + 10 ))
  done

  # Get root password
  info "Retrieving initial root password..."
  sleep 5
  ROOT_PASSWORD=$(docker exec wingman-gitlab \
    grep 'Password:' /etc/gitlab/initial_root_password 2>/dev/null | awk '{print $2}' || echo "")

  if [ -z "$ROOT_PASSWORD" ]; then
    warn "Could not auto-retrieve root password."
    warn "Check: docker exec wingman-gitlab cat /etc/gitlab/initial_root_password"
    warn "Then create a token at: http://localhost:8929/-/user_settings/personal_access_tokens"
    ROOT_PASSWORD="<check-docker-exec-output>"
  fi

  echo ""
  echo "  GitLab URL:       http://localhost:8929"
  echo "  Root password:    ${ROOT_PASSWORD}"
  echo "  (file deleted after 24h — save this password now)"
  echo ""

  # Create API token via rails runner (works without needing an existing token)
  if [ -z "$GITLAB_TOKEN" ]; then
    info "Creating GitLab API token via rails runner..."
    GITLAB_TOKEN=$(docker exec wingman-gitlab \
      gitlab-rails runner \
      "t = User.find_by_username('root').personal_access_tokens.create(name: 'wingman-dev', scopes: ['api','read_repository','write_repository'], expires_at: 365.days.from_now); puts t.token" \
      2>/dev/null | tail -1)

    if [ -n "$GITLAB_TOKEN" ]; then
      info "Token created: ${GITLAB_TOKEN}"
      info "Save this for future helm upgrades."
    else
      warn "Could not auto-create token. Create one manually at:"
      warn "  http://localhost:8929/-/user_settings/personal_access_tokens"
      warn "  Scopes: api, read_repository, write_repository"
      echo -n "Paste token here (or Enter to skip): "
      read -r GITLAB_TOKEN
    fi
  fi
fi

# ── Seed test data ─────────────────────────────────────────────────────────────
if [ "$SKIP_SEED" = false ]; then
  if [ -z "$GITLAB_TOKEN" ]; then
    echo -n "Enter GitLab access token to seed test data (or press Enter to skip): "
    read -r GITLAB_TOKEN
  fi

  if [ -n "$GITLAB_TOKEN" ]; then
    info "Seeding test data..."
    "$PYTHON" scripts/seed-test-data.py \
      --gitlab-url http://localhost:8929 \
      --token "$GITLAB_TOKEN" \
      --no-wait
  else
    warn "Skipping seed — no token provided. Run manually:"
    warn "  python3 scripts/seed-test-data.py --gitlab-url http://localhost:8929 --token <token>"
  fi
fi

# ── Build Docker images ────────────────────────────────────────────────────────
if [ "$SKIP_BUILD" = false ]; then
  info "Building Docker images into minikube..."
  bash scripts/build-images.sh
fi

# ── Deploy Helm chart ──────────────────────────────────────────────────────────
if [ -n "$GITLAB_TOKEN" ]; then
  JWT_SECRET=$(openssl rand -hex 32)
  DEV_SECRET="devpassword"

  info "Deploying Helm chart..."
  helm upgrade --install wingman ./chart \
    -f chart/values.minikube.yaml \
    --set gitlab.accessToken="$GITLAB_TOKEN" \
    --set auth.jwtSecret="$JWT_SECRET" \
    --set devAuth.secret="$DEV_SECRET" \
    -n wingman --create-namespace \
    --wait --timeout=120s

  # ── /etc/hosts entry ─────────────────────────────────────────────────────────
  if ! grep -q "wingman.local" /etc/hosts; then
    info "Adding wingman.local to /etc/hosts (requires sudo)..."
    echo "${MINIKUBE_IP} wingman.local" | sudo tee -a /etc/hosts
  fi

  echo ""
  echo "═══════════════════════════════════════════════════"
  echo "  Wingman is running!"
  echo ""
  echo "  URL:          http://wingman.local"
  echo "  Login:        dev mode — username: admin, password: ${DEV_SECRET}"
  echo "  Role:         admin (full access)"
  echo ""
  echo "  Dev login endpoint: POST /api/auth/dev-login"
  echo "  { \"username\": \"admin\", \"role\": \"admin\", \"secret\": \"${DEV_SECRET}\" }"
  echo "═══════════════════════════════════════════════════"
else
  warn "Skipping Helm deploy — no GitLab token."
  warn "Once you have a token, run:"
  warn "  helm upgrade --install wingman ./chart -f chart/values.minikube.yaml \\"
  warn "    --set gitlab.accessToken=<token> \\"
  warn "    --set auth.jwtSecret=\$(openssl rand -hex 32) \\"
  warn "    --set devAuth.secret=devpassword \\"
  warn "    -n wingman --create-namespace"
fi
