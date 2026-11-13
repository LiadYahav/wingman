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
| `day1.provisioner` | `DAY1_PROVISIONER` | `merge-request` | How a create is proposed (ADR-0042): `merge-request` (Wingman opens the MR) or `workflow` (Wingman starts the platform's `provision-cluster` workflow, which opens it). `workflow` needs `workflows.url` |
| `day1.upgrades.enabled` | `DAY1_UPGRADES` | `false` | Upgrades through the platform's `upgrade-cluster` workflow (ADR-0055): the cluster page starts it, shows its run and sends its decisions, and an edit may no longer change `mastertag` or a `workertag`. Needs `workflows.url`; the workflow must read the same day1 repo as Wingman. On, the Route's timeout is 130 s (`haproxy.router.openshift.io/timeout`), for the targets read |
| `day1.placementMinFreePods` | `PLACEMENT_MIN_FREE_PODS` | `70` | MCE placement (ADR-0050), checked with `clusterStatus.enabled` (without it, not checked): the cost of one hosted control plane. An MCE is offered for a new cluster only with at least this many free pods (allocatable less in use) on its workers: masters, infra nodes and tainted, cordoned or NotReady nodes are left out ([Live cluster status](#live-cluster-status-mce-hubs)) |
| `day1.addServers.enabled` | `DAY1_ADD_SERVERS` | `false` | Inventory Management (ADR-0057): admins add servers to an MCE's InfraEnv pool by starting the platform's `add-server-to-mce` workflow, by count or by name. Needs `workflows.url`; the page needs `serverScan.url`, and the InfraEnvs come from the MCE (`clusterStatus.enabled`) |
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
| `clusterStatus.enabled` | `CLUSTER_STATUS_ENABLED` | `false` | Live status and the cluster nodes, from the MCE hubs ([Live cluster status](#live-cluster-status-mce-hubs)) |
| `clusterStatus.mceDomain` | `MCE_API_DOMAIN` | `""` | A hub is `https://api.{mce}.{mceDomain}:6443`, unless the tokens Secret gives it its own `url` (ADR-0045) |
| `clusterStatus.sslVerify` | `MCE_SSL_VERIFY` | `"false"` | `"true"`, `"false"` or a CA bundle path |
| `clusterStatus.tokensSecretName` | | `mce-sa-tokens` | The Secret whose key `tokens` (a YAML map of MCE name to token, or to `{token, url}`) is mounted as `MCE_TOKENS_FILE` |
| `serverScan.url` | `SERVER_SCAN_URL` | `""` | server-scan's API, e.g. `http://server-scan-api.<ns>.svc:8000`. The nodes' servers, Inventory Management, and the **Server Scan** area for admins ([Cluster nodes](#cluster-nodes-server-scan-and-the-workflows-orchestrator)). Empty: nodes are listed without their servers, no Inventory Management, no Server Scan area |
| `serverScan.uiUrl` | `SERVER_SCAN_UI_URL` | `""` | server-scan's UI, where the node links point. Empty: `serverScan.url` |
| `serverScan.sslVerify` | `SERVER_SCAN_SSL_VERIFY` | `"true"` | `"true"`, `"false"` or a CA bundle path |
| `serverScan.timeoutSeconds` | `SERVER_SCAN_TIMEOUT_SECONDS` | `10` | Per request, at most 60 |
| `serverScan.tokenSecret.name` | `SERVER_SCAN_TOKEN` (day1 only) | `""` | An existing Secret with a server-scan viewer token (every read, the Server Scan area's Sites included). Empty: no token, for a server-scan with auth off |
| `serverScan.tokenSecret.key` | `SERVER_SCAN_TOKEN` (day1 only) | `token` | The token's key in that Secret |
| `serverScan.tokenSecret.adminKey` | `SERVER_SCAN_ADMIN_TOKEN` (day1 only) | `admin-token` | An optional key of the same Secret with server-scan's **admin** token, sent only when an admin turns a server's maintenance on or off on the Server Scan area's Servers page. A Secret without the key still starts day1: the toggle is greyed out with why. Empty: never read. With no Secret at all (auth off) the toggle works without it |
| `workflows.url` | `WORKFLOWS_API_URL` | `""` | The workflows orchestrator, e.g. `http://workflows-orchestrator-api.<ns>.svc:8080`. Empty: no node uninstall. Needs `serverScan.url` |
| `workflows.sslVerify` | `WORKFLOWS_SSL_VERIFY` | `"true"` | `"true"`, `"false"` or a CA bundle path |
| `workflows.timeoutSeconds` | `WORKFLOWS_TIMEOUT_SECONDS` | `10` | Per request, at most 60 |
| `workflows.targetsTimeoutSeconds` | `WORKFLOWS_TARGETS_TIMEOUT_SECONDS` | `65` | An upgrade's targets read, at most 120: the orchestrator waits up to 60 s for it. nginx gives that one path 130 s |
| `segmentsManager.url` | `SEGMENTS_MANAGER_URL` | `""` | segments-manager's API, e.g. `http://segments-manager.<ns>.svc:8000`. The cluster page shows its EPG for the cluster's segment and where it disagrees with the file, and admins get the **Segments** area ([segments-manager](#segments-manager)). Empty: no EPG, no Segments area |
| `segmentsManager.uiUrl` | `SEGMENTS_MANAGER_UI_URL` | `""` | segments-manager's UI. The cluster page links to it and to its search for the cluster's segment. Empty: `segmentsManager.url`; both empty: no link |
| `segmentsManager.sslVerify` | `SEGMENTS_MANAGER_SSL_VERIFY` | `"true"` | `"true"`, `"false"` or a CA bundle path |
| `segmentsManager.timeoutSeconds` | `SEGMENTS_MANAGER_TIMEOUT_SECONDS` | `5` | Per request, at most 60 |
| `quickLinks.hubName` | `QUICK_LINKS_HUB_NAME` | `""` | The hub Wingman runs on, as in `apps.<hubName>.<domain>`: its card on Quick Links ([Quick Links](#quick-links)). Empty: no hub card |
| `quickLinks.hubDomain` | `QUICK_LINKS_HUB_DOMAIN` | `""` | The hub's domain. Empty: `quickLinks.domain` |
| `quickLinks.domain` | `QUICK_LINKS_DOMAIN` | `""` | The MCEs' domain. Empty: `clusterStatus.mceDomain` |
| `quickLinks.argocdUrlTemplate` | `QUICK_LINKS_ARGOCD_URL_TEMPLATE` | `https://openshift-gitops-server-openshift-gitops.apps.{cluster}.{domain}` | A cluster's ArgoCD |
| `quickLinks.consoleUrlTemplate` | `QUICK_LINKS_CONSOLE_URL_TEMPLATE` | `https://console-openshift-console.apps.{cluster}.{domain}` | A cluster's console |
| `quickLinks.clusters` | | `{}` | A cluster's own `argocd` and `console` addresses, for one that does not follow the templates (the ConfigMap `wingman-quick-links`) |
| `quickLinks.sections` | | `[]` | The team's links (the ConfigMap `wingman-quick-links`, re-read by day1 on every page load) |
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

One token, `gitlab.accessToken`, with the `api` scope, of an account that is a member (not an
instance admin without membership: Wingman reads its role from its memberships). It needs:

- the day1 project and the specs project: at least Developer (it pushes branches and opens merge
  requests) and the right to merge into the branches the MRs target;
- each team project in the sigs group (`sigs/<team>`): **per team, the team's choice** (ADR-0043).
  A team that gives the account Developer or higher on its own project is writable in Wingman (new
  add-ons, team and fleet defaults, install, update, remove, approvals); a team that gives it less
  is read-only there, with the reason shown, and every day2 write for it is refused. Reporter is
  enough for its pages to load; with no membership at all, a private project is not seen.

Group membership is inherited: Developer on the sigs group (or a group above it) makes **every**
team writable. For per-team opt-in, give the account Reporter on the sigs group (so every team can
be read) and Developer on each opting-in project, never Developer on the group. Wingman notices a
changed membership within `DAY2_CACHE_TTL_SECONDS`. A team turns its writes on by having a
maintainer of `sigs/<team>` add the account to the project as a Developer, and off by lowering or
removing that membership. `docs/ops/runbook.md` (WingmanGitLabTokenRejected) says how to replace the
token.

### Live cluster status (MCE hubs)

With `clusterStatus.enabled`, day1 reads each MCE hub at `https://api.<mce>.<domain>:6443`
(`clusterStatus.mceDomain`) with that MCE's service-account token, from the Secret
`clusterStatus.tokensSecretName` (key `tokens`, a YAML map of MCE name to token). It reads the
HostedCluster and NodePools for live status, the InfraEnvs for the create form, for a cluster's
nodes (`GET /api/day1/clusters/{name}/nodes`) each NodePool's Machines and Agents, and, for MCE
placement (`GET /api/day1/placement`, ADR-0050), the hub's own nodes and pods.

A hub whose API is not at that address gets its own beside its token (ADR-0045); the plain form
keeps working for the others:

```yaml
ocp4-prod-mce-site1-a: <token>                      # https://api.ocp4-prod-mce-site1-a.<domain>:6443
ocp4-prod-mce-site1-b:
  token: <token>
  url: https://api.hub-b.example.com:6443           # https://<host>[:<port>], nothing after it
```

```bash
oc create secret generic mce-sa-tokens -n <ns> --from-file=tokens=./tokens.yaml \
  --dry-run=client -o yaml | oc apply -f -          # then restart day1: it reads the file at start
```

A `url` that is not `https://<host>[:<port>]` (a path, `http://`, credentials) stops day1 at start,
naming the MCE and never the token.

The service account behind each token needs `get` and `list` on:

| Resources | API group | Namespace |
|---|---|---|
| hostedclusters, nodepools | `hypershift.openshift.io` | `hcp-<clusterName>` |
| machines, machinesets | `cluster.x-k8s.io` | the control plane's, `hcp-<clusterName>-ocp4-<clusterName>` |
| agentmachines | `capi-provider.agent-install.openshift.io` | the control plane's |
| agents, infraenvs | `agent-install.openshift.io` | the HostedCluster's `spec.platform.agent.agentNamespace` |
| nodes, pods (`list` only) | core (`""`) | the whole hub: placement's free pods |

Placement lists the pods as Table rows (name, status, node), only those not `Succeeded` or
`Failed`, never their objects, logs or Secrets. Its servers check lists the Agents of the needed
InfraEnvs across the hub (or in `MCE_INFRAENV_NAMESPACE`): the `agents` rule above already allows
it, because the binding is cluster-wide.

A control-plane namespace is created per cluster, so the grant is a ClusterRole with a
ClusterRoleBinding. Apply it on every hub that has a token, binding the service account whose token
is in the Secret:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: wingman-mce-reader
rules:
  - apiGroups: [hypershift.openshift.io]
    resources: [hostedclusters, nodepools]
    verbs: [get, list]
  - apiGroups: [cluster.x-k8s.io]
    resources: [machines, machinesets]
    verbs: [get, list]
  - apiGroups: [capi-provider.agent-install.openshift.io]
    resources: [agentmachines]
    verbs: [get, list]
  - apiGroups: [agent-install.openshift.io]
    resources: [agents, infraenvs]
    verbs: [get, list]
  - apiGroups: [""]
    resources: [nodes, pods]
    verbs: [list]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: wingman-mce-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: wingman-mce-reader
subjects:
  - kind: ServiceAccount
    name: <service account>
    namespace: <its namespace>
```

```bash
oc apply -f wingman-mce-reader.yaml      # logged in to the hub
oc auth can-i list machines.cluster.x-k8s.io -n hcp-<clusterName>-ocp4-<clusterName> \
  --as=system:serviceaccount:<its namespace>:<service account>   # yes
oc auth can-i list pods --all-namespaces \
  --as=system:serviceaccount:<its namespace>:<service account>   # yes
```

No Secrets: Wingman never reads a hosted cluster's own API, so the drain before an in-place
reboot, and which node goes next, are not shown (`docs/ecosystem/notes/hypershift-node-state.md`).
Without the grant the nodes read answers `502 DEPENDENCY_UNAVAILABLE`, naming the path the hub
denied; with live status off, `501 FEATURE_DISABLED`. Without `list` on nodes and pods, placement
marks that MCE unreadable and never picks it; the other MCEs are not affected. A running Wingman's steps are in
`docs/upgrade/3.3-to-3.4.md`.

### Cluster nodes (server-scan and the workflows orchestrator)

A cluster's nodes come from its MCE ([Live cluster status](#live-cluster-status-mce-hubs)). Both of
these are optional and off by default. With `serverScan.url`, day1 adds each node's server record
from server-scan (health, a link to its page) and the servers server-scan places in the cluster that
no Machine leads to; with `workflows.url`, it also starts the platform's `uninstall-server-from-hc`
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

The same `serverScan.url` turns on the **Server Scan** area for Wingman's admins
(`/server-scan`, from the top bar's area switch; ADR-0048): server-scan's UI rebuilt in
Wingman, one page at a time. Its first page, **Sites**, reads server-scan's own per-site
counts with the same viewer token (no new Secret or key), kept 10 seconds per day1 replica.
Its second, **Servers**, reads the fleet's rows from the cache the Nodes tab already keeps
(`DAY1_CACHE_TTL_SECONDS`), revalidated against server-scan's `ETag`, however many pages
poll. day1 makes the calls; the browser never calls server-scan. Viewers have no
Server Scan area, for now.

The Servers page's **maintenance toggle** is the area's one write, for Wingman's admins
only and logged with the person's name (server-scan records only its token). It needs
server-scan's admin token as a second key of the same Secret
(`serverScan.tokenSecret.adminKey`, default `admin-token`), then a restart of day1:

```bash
oc -n <ns> set data secret/server-scan-viewer admin-token=<server-scan admin token>
oc -n <ns> rollout restart deploy/wingman-day1
```

Without the key the toggle is greyed out and says so; against a server-scan with auth off
(no Secret at all) it works without one. The pages still to come that read server-scan's
event history (auditor) will bring their own key
(`docs/notes/2026-11-13-server-scan-area-api.md` §8, §9).

### segments-manager

Off by default. The cluster page's **HostedCluster & network** card shows the cluster's VLAN and
segment from its file either way (Git is the source of truth, ADR-0039). With
`segmentsManager.url`, day1 also reads that one segment from segments-manager's API (its
reads are open: no token) and shows its EPG, with a warning where
segments-manager disagrees with the file (another VLAN, another cluster, a segment not
Allocated, or none). day1 never writes to segments-manager, and segments-manager down only
hides the EPG.

The same setting turns on the **Segments** area for Wingman's admins (`/segments`, from the top
bar's area switch; ADR-0047): segments-manager's page rebuilt in Wingman, read only, from its
open reads of the sites, the per-site statistics and the segments (and a fresh read for
Refresh, at most once per 5 seconds per replica). day1 makes the calls, so only day1 needs to
reach `url`; the browser never calls segments-manager. Viewers have no Segments area, for now.

The card also links to segments-manager's UI, names the cluster to search for there (its UI
opens no single cluster), and links to its open search API for the cluster's segment as JSON.
The links use `uiUrl`, or `url` when `uiUrl` is empty; the browser needs to reach them.

```yaml
segmentsManager:
  url: http://segments-manager.<ns>.svc:8000
  uiUrl: https://segments-manager.example
```

A running 3.4 adds it with `docs/upgrade/3.4-to-3.5.md`.

### Quick Links

The **Quick Links** page (`/quick-links`, admins only) is a launcher: a card for the hub Wingman
runs on (`quickLinks.hubName`) and one for every MCE of the day1 repo, by site, each opening the
cluster's ArgoCD with its console beside it, at `quickLinks.argocdUrlTemplate` and
`quickLinks.consoleUrlTemplate` in `quickLinks.domain` (default `clusterStatus.mceDomain`). Then
the team's own links, `quickLinks.sections`. With a domain set, every MCE has its card and nothing
else is needed.

Wingman only lists the links: neither day1 nor the browser calls them, so the page shows no
status dots and no ArgoCD application counts (both removed in 3.13.1; the ArgoCD shows its own
counts one click away). day1 needs no route to the links, and no token for any of them. Values
kept from 3.9 to 3.13.0 that still set the checks or the ArgoCD tokens are ignored; what to
delete is at the top of `docs/upgrade/3.8-to-3.9.md`.

`quickLinks.sections` and `quickLinks.clusters` are rendered into the ConfigMap
`wingman-quick-links`, mounted in day1 as a directory. day1 reads it on every page load, so an
edit (`helm upgrade`, or `oc edit cm wingman-quick-links`) shows within about a minute, without a
restart. A mistake in it never breaks the page: the page lists each problem and shows the rest.
The file's shape and every icon key: `docs/notes/2026-11-12-quick-links-api.md`.

```yaml
quickLinks:
  hubName: hub-prod
  clusters:                       # a cluster that does not follow the templates
    hub-prod:
      console: https://console.hub-prod.example.internal
  sections:
    - name: Core GitOps
      columns: 2                  # 1 to 6, default 4
      links:
        - name: GitLab GitOps Project
          url: https://gitlab.example.internal/platform/gitops
          description: Main GitOps repository
          icon: gitlab
        - name: ArgoCD Main
          url: https://argocd.example.internal
          icon: argocd
```

A running Wingman adds all of this with `docs/upgrade/3.8-to-3.9.md`.

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

If pods restart due to liveness probe timeouts, or never become ready:
- Liveness is `/health/live` (the process answers); readiness is
  `/health/ready`, which also needs GitLab to answer once after the pod
  starts (ADR-0054). A pod that is live but never ready cannot reach GitLab,
  or the token cannot read what the service checks: day1 the
  `gitlab.day1ProjectId` and `gitlab.specsProjectId` projects, day2 the
  `gitlab.day2SigsGroupPath` group and the day1 project. Check `gitlab.url`,
  the token, those values and the CA; `/health/ready` on the pod's port names
  the error.
- Once ready, a pod stays ready through a GitLab outage: readiness no longer
  asks GitLab, so users get Wingman's own error (a 503 `GIT_UNAVAILABLE`
  problem) instead of a proxy error page, and cached reads still answer for
  up to a minute. The GitLab alerts (`docs/ops/runbook.md`) report the outage.
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
