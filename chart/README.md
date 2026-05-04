# Wingman Helm Chart

Helm chart for deploying the Wingman platform on Kubernetes/OpenShift.

## Prerequisites

- Kubernetes 1.24+ or OpenShift 4.12+
- Helm 3.x
- Access to GitLab instance with configured repositories
- (Optional) GitLab OAuth application for SSO

## Quick Start

### Local Development (Minikube)

```bash
# Start minikube with ingress
minikube start --cpus=4 --memory=8g
minikube addons enable ingress

# Create namespace
kubectl create namespace wingman

# Build and load images into minikube
eval $(minikube docker-env)
docker build -t wingman-day1:latest -f apps/day1-service/Dockerfile .
docker build -t wingman-day2:latest -f apps/day2-service/Dockerfile .
docker build -t wingman-web:latest apps/web/

# Install with minikube values
helm upgrade --install wingman ./chart \
  --namespace wingman \
  -f chart/values.minikube.yaml

# Access via minikube tunnel
minikube tunnel
# Then open http://localhost:8080
```

### Production (OpenShift)

```bash
# Create namespace
oc new-project wingman

# Create secrets for GitLab tokens
oc create secret generic wingman-secrets \
  --from-literal=GITLAB_DAY1_TOKEN=<your-day1-token> \
  --from-literal=GITLAB_DAY2_TOKEN=<your-day2-token> \
  --from-literal=GITLAB_SPECS_TOKEN=<your-specs-token> \
  --from-literal=OAUTH_CLIENT_SECRET=<your-oauth-secret>

# Install with production values
helm upgrade --install wingman ./chart \
  --namespace wingman \
  -f chart/values.yaml \
  --set global.gitlab.url=https://gitlab.your-company.com \
  --set global.baseDomain=wingman.your-company.com
```

## Configuration

### Key Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.gitlab.url` | GitLab instance URL | `https://gitlab.com` |
| `global.baseDomain` | Base domain for routes | `wingman.local` |
| `day1.gitlab.projectId` | Day1 GitLab project path | `wingman/day1-clusters` |
| `day2.gitlab.sigsGroupPath` | Day2 SIGs group path | `wingman/sigs` |
| `specs.gitlab.projectId` | Specs GitLab project path | `wingman/specs` |
| `web.replicas` | Web frontend replicas | `1` |

### Image Configuration

For air-gapped environments, override image sources:

```yaml
day1:
  image:
    repository: your-registry.local/wingman/day1
    tag: latest
    pullPolicy: IfNotPresent

day2:
  image:
    repository: your-registry.local/wingman/day2
    tag: latest

web:
  image:
    repository: your-registry.local/wingman/web
    tag: latest
```

### GitLab OAuth (SSO)

1. Create an OAuth application in GitLab (Admin > Applications)
2. Set callback URL to `https://<your-domain>/api/auth/callback`
3. Enable scopes: `openid`, `profile`, `email`, `read_user`
4. Configure in values:

```yaml
oauth:
  enabled: true
  clientId: <application-id>
  # clientSecret via secret
```

## Loading Pre-built Images (Air-gapped)

```bash
# On build machine
docker save wingman-day1:latest | gzip > wingman-day1.tar.gz
docker save wingman-day2:latest | gzip > wingman-day2.tar.gz
docker save wingman-web:latest | gzip > wingman-web.tar.gz

# Transfer to air-gapped environment, then:
docker load < wingman-day1.tar.gz
docker load < wingman-day2.tar.gz
docker load < wingman-web.tar.gz

# Tag and push to internal registry
docker tag wingman-day1:latest your-registry.local/wingman/day1:latest
docker push your-registry.local/wingman/day1:latest
# ... repeat for other images
```

## Troubleshooting

### Health Check Failures

If pods restart due to liveness probe timeouts:
- Check GitLab connectivity from pods
- Increase probe timeouts in values.yaml
- Check cache warming logs: `kubectl logs -f deploy/wingman-day2`

### GitLab API Errors

Verify tokens have correct scopes:
- Day1/Specs: `api` or `read_repository`, `write_repository`
- Day2: `api` (needs group access)

### SSL/TLS Issues

For self-signed GitLab certificates:
```yaml
global:
  gitlab:
    sslVerify: false  # Or path to CA bundle
```

## Uninstall

```bash
helm uninstall wingman -n wingman
kubectl delete namespace wingman
```
