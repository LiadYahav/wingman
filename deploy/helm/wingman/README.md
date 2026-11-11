# Wingman Helm Chart

Helm chart for deploying the Wingman platform on OpenShift (or, for local use, Kubernetes).

## Prerequisites

- OpenShift 4.12+ (the chart creates a Route and an `OAuthClient`), or Kubernetes 1.24+ with an
  ingress controller and dev login, for local use only
- Helm 3.x
- A GitLab with the day1 project, the specs project and the sigs group of team projects, and a
  service account token for them (see [GitLab token](#gitlab-token))
- (Optional) the Prometheus Operator CRDs, for monitoring (`docs/ops/metrics.md`)

## Quick Start

### Local Development (Minikube)

`scripts/minikube-dev-setup.sh` does all of this, including a local GitLab seeded with the
fixture repos. By hand:

```bash
minikube start --cpus=4 --memory=8g
minikube addons enable ingress

# Build the images into minikube (scripts/build-images.sh does the same)
eval $(minikube docker-env)
docker build -t wingman-day1:latest -f apps/day1-service/Dockerfile .
docker build -t wingman-day2:latest -f apps/day2-service/Dockerfile .
docker build -t wingman-web:latest -f apps/web/Dockerfile .

# Install with the minikube values: dev login, an Ingress, the local GitLab
helm upgrade --install wingman ./deploy/helm/wingman -n wingman --create-namespace \
  -f deploy/helm/wingman/values.minikube.yaml \
  --set gitlab.accessToken=<token> \
  --set auth.jwtSecret=$(openssl rand -hex 32) \
  --set devAuth.secret=$(openssl rand -hex 16)

# Add "$(minikube ip) wingman.local" to /etc/hosts, then open http://wingman.local
```

### Production (OpenShift)

The chart renders the `wingman-secrets` Secret and the `OAuthClient` from its values: pass the
secrets as values, and do not create that Secret yourself.

```bash
oc new-project wingman

helm upgrade --install wingman ./deploy/helm/wingman -n wingman \
  --set gitlab.url=https://gitlab.example.com \
  --set gitlab.accessToken=<token> \
  --set gitlab.day1ProjectId=gitops-day1/platform-config \
  --set gitlab.specsProjectId=wingman/cluster-specs \
  --set gitlab.day2SigsGroupPath=gitops-day2-prod/sigs \
  --set auth.openshiftOAuthHost=oauth-openshift.apps.example.com \
  --set auth.openshiftApiHost=api.example.com:6443 \
  --set auth.jwtSecret=$(openssl rand -hex 32) \
  --set auth.oauthClientSecret=$(openssl rand -hex 32) \
  --set route.host=wingman.apps.example.com \
  --set image.day1.tag=<version> --set image.day2.tag=<version> --set image.web.tag=<version>
```

Keep the generated secrets for later upgrades (in a values file outside Git, passed with `-f`):
a new `auth.jwtSecret` signs everyone out.

## Configuration

### Key Values

Every variable the services read is set from these (`templates/configmap.yaml`, `templates/secret.yaml`,
and day1's `env` in `templates/day1-deployment.yaml` for the server-scan token);
the names are explained in the root README's [Environment Variables](../README.md#environment-variables).

| Key | Sets | Default | Description |
|-----|------|---------|-------------|
| `gitlab.url` | `GITLAB_URL` | `https://gitlab.internal` | The GitLab instance |
| `gitlab.accessToken` | `GITLAB_TOKEN` (Secret) | `""` | The one service account token ([GitLab token](#gitlab-token)) |
| `gitlab.day1ProjectId` | `DAY1_GITLAB_PROJECT_ID` | `""` | The day1 project: a numeric id or a `group/project` path |
| `gitlab.specsProjectId` | `SPECS_GITLAB_PROJECT_ID` | `""` | The specs project |
| `gitlab.specsRoot` | `SPECS_ROOT_PATH` | `specs` | The spec files' folder in the specs project |
| `gitlab.day2SigsGroupPath` | `DAY2_SIGS_GROUP_PATH` | `""` | The sigs group: every project directly in it is a team |
| `gitlab.day2GitopsBranch` | `DAY2_GITOPS_BRANCH` | `main` | The branch the platform reads; day2's MRs target it |
| `gitlab.verifyTls` | `GITLAB_VERIFY_TLS` | `true` | An internal CA goes in `tls.caBundle`, not here |
| `gitlab.webhookSecret` | `GITLAB_WEBHOOK_SECRET` (Secret) | `""` | Empty: day1's GitLab webhook answers 404 |
| `environment` | `WINGMAN_ENVIRONMENT` | `production` | `production` refuses the in-memory GitLab (ADR-0009) |
| `day1.clusterNameStripPrefix` | `DAY1_CLUSTER_NAME_STRIP_PREFIX` | `ocp4-` | ADR-0015: `""` for the GitHub sandbox |
| `day1.cacheTtlSeconds` | `DAY1_CACHE_TTL_SECONDS` | `30` | Per replica, at most 60 (ADR-0011) |
| `day2.cacheTtlSeconds` | `DAY2_CACHE_TTL_SECONDS` | `15` | Per replica, at most 60 (ADR-0011) |
| `auth.openshiftOAuthHost` | `OPENSHIFT_OAUTH_HOST` | | The OAuth server's host ([Login](#login-openshift-oauth)) |
| `auth.openshiftApiHost` | `OPENSHIFT_API_HOST` | | The API server, `host:port` |
| `auth.oauthClientId` | `OPENSHIFT_OAUTH_CLIENT_ID` | `wingman-app` | Also the name of the `OAuthClient` the chart creates |
| `auth.oauthClientSecret` | `OPENSHIFT_OAUTH_CLIENT_SECRET` (Secret) | `""` | Also the `OAuthClient`'s secret |
| `auth.oauthRedirectUri` | `OPENSHIFT_OAUTH_REDIRECT_URI` | `""` | Empty: `https://{route.host}/login` |
| `auth.sslVerify` | `OPENSHIFT_SSL_VERIFY` | `"false"` | `"true"`, `"false"` or a CA bundle path |
| `auth.jwtSecret` | `JWT_SECRET_KEY` (Secret) | `""` | At least 32 characters: `openssl rand -hex 32` |
| `auth.jwtExpiryHours` | `JWT_EXPIRY_HOURS` | `8` | How long a session lasts |
| `auth.adminGroups` | `WINGMAN_ADMIN_GROUPS` | `wingman-admins` | Comma-separated OpenShift groups |
| `auth.viewerGroups` | `WINGMAN_VIEWER_GROUPS` | `""` | Empty: no viewer role |
| `devAuth.enabled` | `DEV_AUTH_ENABLED` | `false` | Dev login instead of OpenShift: local use only |
| `devAuth.secret` | `DEV_AUTH_SECRET` (Secret) | `""` | At least 32 characters |
| `clusterStatus.enabled` | `CLUSTER_STATUS_ENABLED` | `false` | Live status from the MCE hubs |
| `clusterStatus.mceDomain` | `MCE_API_DOMAIN` | `""` | A hub is `https://api.{mce}.{mceDomain}:6443` |
| `clusterStatus.sslVerify` | `MCE_SSL_VERIFY` | `"false"` | `"true"`, `"false"` or a CA bundle path |
| `clusterStatus.tokensSecretName` | | `mce-sa-tokens` | The Secret whose key `tokens` (a YAML map of MCE name to token) is mounted as `MCE_TOKENS_FILE` |
| `serverScan.url` | `SERVER_SCAN_URL` | `""` | server-scan's API, e.g. `http://server-scan-api.<ns>.svc:8000`. Empty: no cluster nodes ([Cluster nodes](#cluster-nodes-server-scan-and-the-workflows-orchestrator)) |
| `serverScan.uiUrl` | `SERVER_SCAN_UI_URL` | `""` | server-scan's UI, where the node links point. Empty: `serverScan.url` |
| `serverScan.sslVerify` | `SERVER_SCAN_SSL_VERIFY` | `"true"` | `"true"`, `"false"` or a CA bundle path |
| `serverScan.timeoutSeconds` | `SERVER_SCAN_TIMEOUT_SECONDS` | `10` | Per request, at most 60 |
| `serverScan.tokenSecret.name` | `SERVER_SCAN_TOKEN` (day1 only) | `""` | An existing Secret with a server-scan viewer token. Empty: no token, for a server-scan with auth off |
| `serverScan.tokenSecret.key` | `SERVER_SCAN_TOKEN` (day1 only) | `token` | The token's key in that Secret |
| `workflows.url` | `WORKFLOWS_API_URL` | `""` | The workflows orchestrator, e.g. `http://workflows-orchestrator-api.<ns>.svc:8080`. Empty: no node uninstall. Needs `serverScan.url` |
| `workflows.sslVerify` | `WORKFLOWS_SSL_VERIFY` | `"true"` | `"true"`, `"false"` or a CA bundle path |
| `workflows.timeoutSeconds` | `WORKFLOWS_TIMEOUT_SECONDS` | `10` | Per request, at most 60 |
| `tls.caBundle` | | `""` | An internal CA (PEM), mounted in every pod |
| `tls.caBundleMountPath` | `SSL_CERT_FILE` | `/etc/pki/tls/certs/ca-bundle.crt` | Where it is mounted (set only with a `tls.caBundle`) |
| `route.host` | | `wingman.apps.your-cluster.internal` | The Route's host |
| `openshiftRoute.enabled` | | `true` | A Route and the `OAuthClient`; `false` on plain Kubernetes |
| `ingress.enabled` | | `false` | An Ingress instead (`ingress.host`, `ingress.className`) |
| `image.registry` | | `""` | Prefix of every image: `<registry>/<repository>:<tag>` |
| `image.{day1,day2,web,nginx}.{repository,tag,pullPolicy}` | | `latest` tags | In production, pin day1, day2 and web to one release (`3.0.1`, docs/ops/images.md) |
| `replicaCount.{day1,day2,web,nginx}` | | `1` | |
| `imagePullSecret` | | `""` | An existing registry Secret |
| `monitoring.{serviceMonitor,prometheusRule,grafanaDashboard}.enabled` | | `false` | `docs/ops/metrics.md`, `docs/ops/runbook.md` |

`values.yaml` has the rest (resources, the service account) with comments.

### Image Configuration

For air-gapped environments, mirror the images and point the chart at the mirror:

```yaml
image:
  registry: registry.example.com/wingman
  day1:
    repository: wingman-day1
    tag: "<version>"     # a release, e.g. "3.0.1"
  day2:
    repository: wingman-day2
    tag: "<version>"     # a release, e.g. "3.0.1"
  web:
    repository: wingman-web
    tag: "<version>"     # a release, e.g. "3.0.1"
  nginx:
    repository: nginx      # mirror it too
    tag: "<pinned tag>"
```

### Login (OpenShift OAuth)

Users sign in with OpenShift, and their OpenShift groups decide their role (`auth.adminGroups`,
`auth.viewerGroups`). With `openshiftRoute.enabled` and without `devAuth.enabled`, the chart
creates an `OAuthClient` named `auth.oauthClientId` with the secret `auth.oauthClientSecret` and the
redirect URI `https://{route.host}/login` (or `auth.oauthRedirectUri`); the installing user needs
the right to create that cluster-scoped resource. Set:

- `auth.openshiftOAuthHost`: `oc get route oauth-openshift -n openshift-authentication -o jsonpath='{.spec.host}'`
- `auth.openshiftApiHost`: `oc whoami --show-server`, without `https://`

`devAuth` replaces OpenShift login with a shared secret, for minikube and local use only.

### GitLab token

One token, `gitlab.accessToken`, with the `api` scope. Its account must be a member of the day1
project, the specs project and every team project in the sigs group, with at least the Developer
role (it pushes branches and opens merge requests) and the right to merge into the branches the
MRs target. `docs/ops/runbook.md` (WingmanGitLabTokenRejected) says how to replace it.

### Cluster nodes (server-scan and the workflows orchestrator)

Both are off by default. With `serverScan.url`, day1 lists the servers under each hosted cluster
from server-scan; with `workflows.url`, it also starts the platform's `uninstall-server-from-hc`
workflow for one of them and shows its run. The orchestrator has no auth. An uninstall checks the
server in server-scan first, so `workflows.url` without `serverScan.url` fails the chart.

The server-scan token never goes in values: put a viewer token in a Secret and name the Secret.

```bash
oc create secret generic server-scan-viewer -n wingman --from-literal=token=<token>
```

```yaml
serverScan:
  url: http://server-scan-api.<ns>.svc:8000
  uiUrl: https://server-scan.example      # where the node links point
  tokenSecret: { name: server-scan-viewer }
workflows:
  url: http://workflows-orchestrator-api.<ns>.svc:8080
```

day1 reads the token at start: restart it (`oc rollout restart deploy/wingman-day1`) after
replacing the Secret.

## Loading Pre-built Images (Air-gapped)

```bash
VERSION=3.0.1   # the release, built as the README's Docker section shows

# On build machine
docker save wingman-day1:$VERSION | gzip > wingman-day1-$VERSION.tar.gz
docker save wingman-day2:$VERSION | gzip > wingman-day2-$VERSION.tar.gz
docker save wingman-web:$VERSION | gzip > wingman-web-$VERSION.tar.gz

# Transfer to air-gapped environment, then:
docker load < wingman-day1-$VERSION.tar.gz
docker load < wingman-day2-$VERSION.tar.gz
docker load < wingman-web-$VERSION.tar.gz

# Tag and push to internal registry
docker tag wingman-day1:$VERSION registry.example.com/wingman/wingman-day1:$VERSION
docker push registry.example.com/wingman/wingman-day1:$VERSION
# ... repeat for the other images
```

## Troubleshooting

### Health Check Failures

If pods restart due to liveness probe timeouts:
- Liveness is `/health/live` (the process answers); readiness is
  `/health/ready`, which also needs GitLab to answer. A pod that is live but
  not ready cannot reach GitLab: check `gitlab.url`, the token and the CA.
- `kubectl logs deploy/wingman-day1` (or `-day2`): a configuration the
  service refuses (ADR-0009) is logged at start-up, and the pod exits.

### GitLab API Errors

A 401 or 403 from GitLab to every user means the token: see [GitLab token](#gitlab-token).

### SSL/TLS Issues

For an internal CA, paste it into `tls.caBundle`; it is mounted in every pod
and named by `SSL_CERT_FILE`. `gitlab.verifyTls: false` turns verification
off (never in production).

## Uninstall

```bash
helm uninstall wingman -n wingman
kubectl delete namespace wingman
```
