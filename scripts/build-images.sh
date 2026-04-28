#!/usr/bin/env bash
# Build all Wingman Docker images into minikube's Docker daemon.
# Run from the repo root (cluster-platform/).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TAG="${TAG:-latest}"

echo "==> Pointing Docker to minikube's daemon..."
eval "$(minikube docker-env)"

echo ""
echo "==> Building wingman-day1:${TAG}"
docker build -f apps/day1-service/Dockerfile -t "wingman-day1:${TAG}" .

echo ""
echo "==> Building wingman-day2:${TAG}"
docker build -f apps/day2-service/Dockerfile -t "wingman-day2:${TAG}" .

echo ""
echo "==> Building wingman-web:${TAG}"
docker build -f apps/web/Dockerfile -t "wingman-web:${TAG}" apps/web/

echo ""
echo "==> Images loaded into minikube:"
minikube image ls | grep wingman || true
echo ""
echo "Done. Now deploy with:"
echo "  helm upgrade --install wingman ./chart -f chart/values.minikube.yaml \\"
echo "    --set gitlab.accessToken=<your-token> \\"
echo "    --set auth.jwtSecret=\$(openssl rand -hex 32) \\"
echo "    --set devAuth.secret=devpassword \\"
echo "    -n wingman --create-namespace"
