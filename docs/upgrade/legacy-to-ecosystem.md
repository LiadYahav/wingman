# Upgrade: the legacy services → the rewrite on wingman-core

For an agent inside the disconnected environment. Follow the steps in order.
Every check says what to do when it fails, and **STOP** means: change
nothing, finish the report (step 10) and hand it back.

Throughout:
- `<ns>` is the namespace Wingman runs in, and `<release>` its Helm release.
- `<registry>` is the internal container registry.
- `<tag>` is the release you deploy, as its image tag: a version such as `3.0.1`
  (the GitHub release and git tag `v3.0.1`, without the `v`). Never `latest`,
  `3.0`, `3` or a `sha-` tag: they move, or name no release (`docs/ops/images.md`).
- `$CHART` is the `deploy/helm/wingman/` directory of the repository copy at that release
  (git tag `v<tag>`).

## 1. What changes

| Area | Before | After |
|---|---|---|
| Services | `src.main:app` in each image | `wingman_day1.main:app`, `wingman_day2.main:app` on `wingman-core`. Same ports (day1 8001, day2 8002) and the same `/api/...` paths behind nginx. |
| GitLab token | `GITLAB_ACCESS_TOKEN` | `GITLAB_TOKEN`. Same value, new name. |
| TLS to GitLab | `GITLAB_SSL_VERIFY` (true, false or a CA path), `REQUESTS_CA_BUNDLE` | `GITLAB_VERIFY_TLS` (true or false). An internal CA goes in `tls.caBundle`, which the chart mounts and names in `SSL_CERT_FILE`. |
| Paths inside repos | `DAY1_CLUSTERS_PATH_TEMPLATE`, `DAY1_CLUSTER_FILE_SUFFIX`, `DAY2_ADDON_*_PATH_TEMPLATE` | Gone. The layouts are the platform's contract, fixed in code (ADR-0020). |
| Caches | eleven `CACHE_*` variables | `DAY1_CACHE_TTL_SECONDS` and `DAY2_CACHE_TTL_SECONDS`, at most 60 (ADR-0011) |
| Cluster name prefix | `MCE_CLUSTER_NAME_PREFIX` (`clusterStatus.clusterNamePrefix`) | `DAY1_CLUSTER_NAME_STRIP_PREFIX` (`day1.clusterNameStripPrefix`, default `ocp4-`). The old name is still read. |
| Default branch | `GITLAB_DEFAULT_BRANCH` | day1 uses each project's default branch from GitLab; day2 uses `DAY2_GITOPS_BRANCH` (`gitlab.day2GitopsBranch`, default `main`) |
| Runtime | — | `WINGMAN_ENVIRONMENT` (`environment`, default `production`). Production refuses the in-memory GitLab and a weak dev login. |
| Probes | `/healthz` | `/health/live` (the process) and `/health/ready` (GitLab answered once since the pod started, ADR-0054). `/healthz` still answers. |
| Monitoring | — | A ServiceMonitor, alert rules and a Grafana dashboard, all off by default (`monitoring.*`) |
| The specs project's `cluster-template.j2` | Rendered as is | **Every rendered file is checked against the values-file contract** before an MR is opened (ADR-0012). The template must produce the new chart's values: see check 4.4. |
| Day2 repos | `operators/<addon>` plus `mces/<mce>/<cluster>/<addon>` at the repo root | The gitops-day2 layout: `sites/<site>/<env>/mces/<mce>/<cluster>/<chart>/`, `defaults/<kind>/<chart>/`, `operators/<chart>/`, `exclusions.yaml`. See check 4.3. |
| Drift | Compared files; had a "Sync YAML" button | Only a missing spec addon is drift. Another version is shown as information (ADR-0016, ADR-0025). |
| Sites and MCEs | Could be created from the UI | Read-only. Wingman never creates them (ADR-0018). |

Unchanged:
- OAuth: the OAuthClient, the OpenShift groups, and `JWT_SECRET_KEY` shared by both services.
- The Route or Ingress.
- The MCE tokens Secret for live status.
- The webhook secret.
- The branch, title and description formats of Wingman's MRs (ADR-0007), so MRs opened by the old version still show on the approvals page.

## 2. What to bring in from the connected side

1. **The repository** at the release you deploy (git tag `v<tag>`), as an
   archive. You need `deploy/helm/wingman/`, `docs/` and
   `dev/gitlab-fixtures/wingman/cluster-specs/cluster-template.j2`.
2. **The three images** of that release: `wingman-day1`, `wingman-day2` and
   `wingman-web`, all with the same `<tag>`. Choose one way:
   - **Built by CI (preferred).** CI pushes `ghcr.io/<owner>/wingman-<name>:<tag>`
     for every release, and every merge to main is one (`docs/ops/images.md`).
     On the connected side, verify the provenance of the version tag and save
     each image:
     ```bash
     gh attestation verify oci://ghcr.io/<owner>/wingman-day1:<tag> --owner <owner>   # <tag> = 3.0.1, say
     skopeo copy --all docker://ghcr.io/<owner>/wingman-day1:<tag> oci-archive:wingman-day1-<tag>.tar
     ```
     Inside, push each archive to the internal registry:
     ```bash
     skopeo copy --all oci-archive:wingman-day1-<tag>.tar docker://<registry>/wingman-day1:<tag>
     ```
   - **Built inside.** The Dockerfiles need, from internal mirrors:
     - the UBI base images by digest;
     - the CPython tarball (`--build-arg PYTHON_BUILD_STANDALONE_URL=<internal store>`; the pinned checksum still decides what is accepted);
     - a PyPI mirror holding every wheel in `deploy/python/*.txt`;
     - an npm mirror for the root `package-lock.json`.

     Build from the repository root (`docs/ops/images.md`) with
     `--build-arg VERSION=<tag> --build-arg COMMIT=$(git rev-parse "v<tag>^{commit}")`,
     and name each image `<tag>`.
3. **Nothing else.** The nginx image the chart already uses stays.

## 3. Discover what runs (read-only)

Save each output in a working folder, for the report:

```bash
helm list -n <ns>
helm history <release> -n <ns>                      # the revision you can roll back to
helm get values <release> -n <ns> -o yaml > current-values.yaml   # holds secrets: never print it, never hand it back
kubectl -n <ns> get deploy -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[*].image
kubectl -n <ns> get configmap wingman-config -o yaml > current-config.yaml
```

Note:
- the image tags running now;
- the chart revision;
- whether these are set: `clusterStatus.enabled`, `tls.caBundle`, `devAuth.enabled`.

**STOP** if `devAuth.enabled` is true in production: that is a finding for
a person, not something to carry forward.

## 4. Check the preconditions (read-only)

### 4.1 The GitLab token

The value of `gitlab.accessToken` becomes `GITLAB_TOKEN`. It needs the `api`
scope. Wingman reads and writes repositories and opens and merges MRs, as it
does now. Check that it still works:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "PRIVATE-TOKEN: $TOKEN" "<gitlab>/api/v4/projects/<url-encoded day1 project>"
```

Set `$TOKEN` from the Secret without echoing it. **STOP** on anything but 200.

### 4.2 The day1 repo and the cluster name rule

- Files live at `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` in
  `gitlab.day1ProjectId`. **STOP** if the repo uses another layout: the
  path is no longer a setting.
- `day1.clusterNameStripPrefix` must match what the tier-3 ApplicationSet
  passes as `clusterName` (ADR-0015). Production strips `ocp4-` from the
  file name: check the ApplicationSet template (`hcAppset.yaml` in the
  argocd-platform repo). If it strips `ocp4-`, keep the default; if it
  passes the whole file stem, set `""`. Live status and the HostedCluster
  names Wingman shows depend on it.

### 4.3 The day2 repos' layout

For every project directly in `gitlab.day2SigsGroupPath` (each one is a
team):
- **Expected:** `sites/<site>/<env>/...` (env is `prod`, `prep` or `test`),
  with `mces/<mce>/<cluster>/<chart>/` under it, plus `defaults/` and
  `operators/`.
- **The old layout:** `mces/<mce>/<cluster>/<addon>` at the repo root.

**STOP** if any team repo still has the old layout. The new day2 can't read
or write it, and nothing in Wingman converts it. Report which repos.

### 4.4 The specs project

In `gitlab.specsProjectId`:
- `cluster-template.j2` at the project root;
- the specs in `gitlab.specsRoot` (default `specs/`), one `<name>.yaml` each.

`openshift-versions.txt` is no longer read; delete it once the new day1 is
up. The OpenShift versions come from the day1 repo now (ADR-0034). In
`gitlab.day1ProjectId`:
- `upgrade/ladder.yaml`, the verified releases (`ladder[].version`);
- one `upgrade/mces/<mce>.yaml` for every MCE that clusters are created on,
  with the minors it can host (`mce.supportedHostedVersions`, quoted).

An MCE without its file offers no versions, and the create form says so for
that MCE. The day1 repo's `upgrade/README.md` describes both files.

The new day1 checks every rendered file before it opens an MR (ADR-0012):
- it needs a valid `mastertag` and a `nodepool[]` list;
- it refuses the keys the file's path gives: `clusterName`, `site`, `mce`;
- it refuses the keys automation writes: `vlanId`, `dhcp_values`, `mcFiles`, `mcConfigMap`.

A template written for the old services may fail this. Compare the project's template with
the repository's `dev/gitlab-fixtures/wingman/cluster-specs/cluster-template.j2`:

- **Same:** nothing to do.
- **Different:** step 6 replaces it through an MR. First check that the new
  template renders a valid file for this environment's chart. Render it for
  one existing cluster's inputs, then run the chart on the result exactly as
  ArgoCD does:
  ```bash
  helm template <cluster> <hostedclusters-setup chart dir> \
    -f sites/configValues.yaml -f sites/<site>/values.yaml \
    -f sites/<site>/mces/<mce>/values.yaml -f <rendered cluster file> \
    --set-string clusterName=<cluster without the strip prefix>,site=<site>,mce=<mce>
  ```
  **STOP** if `helm template` fails, or if the HostedCluster and NodePools
  differ from that cluster's real ones in anything but the values you
  changed.

Existing spec files keep loading: the legacy shape is accepted (ADR-0013).
After the upgrade, the Specs page shows any spec that doesn't load, with its
reason.

### 4.5 Open MRs from the old version

List them. The formats are unchanged, so they stay reviewable. Still, a
quieter switch is better: ask the owners to merge or close what is ready.
Don't merge anything yourself.

## 5. Write the new values file

Start from `current-values.yaml` and change only these keys:

| Old key | New key | Note |
|---|---|---|
| `gitlab.sslVerify` | `gitlab.verifyTls` | `true` or `false` only. If it held a CA path, put that CA (PEM) in `tls.caBundle` and set `verifyTls: true` |
| `gitlab.defaultBranch` | `gitlab.day2GitopsBranch` | day2's target branch; day1 asks GitLab |
| `paths.specsRoot` | `gitlab.specsRoot` | |
| `paths.*` (the rest) | — | delete; fixed in code |
| `cache.*` | `day1.cacheTtlSeconds`, `day2.cacheTtlSeconds` | delete `cache`; the defaults (30, 15) are fine |
| `clusterStatus.clusterNamePrefix` | `day1.clusterNameStripPrefix` | the value from check 4.2 |
| — | `environment: production` | the default |
| `gitlab.accessToken` | `gitlab.accessToken` | same key; the chart now writes it as `GITLAB_TOKEN` |

Leave `auth.*`, `devAuth.*`, `route`, `openshiftRoute`, `ingress`, `tls`,
`clusterStatus.*` (except the prefix), `replicaCount` and `resources` as
they are. Set the images:

```yaml
image:
  registry: <registry>
  day1: { repository: wingman-day1, tag: "<tag>" }
  day2: { repository: wingman-day2, tag: "<tag>" }
  web:  { repository: wingman-web,  tag: "<tag>" }
```

Keep secrets out of the file you keep: pass them with `--set` from the
existing Secret, or from a values file you delete afterwards.

## 6. Change GitLab (only if check 4.4 said so)

Open an MR on the specs project that replaces `cluster-template.j2` with
the checked one. A person with rights merges it right before the Helm
upgrade. The old services render with the new template from that moment,
so keep the window short. Record the MR.

## 7. Render, compare, upgrade

```bash
helm template <release> "$CHART" -n <ns> -f new-values.yaml > new.yaml
helm get manifest <release> -n <ns> > old.yaml
diff <(grep -v '^#' old.yaml) <(grep -v '^#' new.yaml) > manifest.diff   # read it; secrets show only as base64 Secret data
```

In `wingman-config`, expect these keys to go:
- `CACHE_*`, `DAY1_CLUSTERS_PATH_TEMPLATE`, `DAY1_CLUSTER_FILE_SUFFIX`;
- `DAY2_ADDON_DEFS_PATH_TEMPLATE`, `DAY2_ADDON_OVERRIDES_PATH_TEMPLATE`, `DAY1_SERVICE_URL`;
- `GITLAB_DEFAULT_BRANCH`, `GITLAB_SSL_VERIFY`, `MCE_CLUSTER_NAME_PREFIX`, `REQUESTS_CA_BUNDLE`.

Expect these to arrive:
- `DAY1_CACHE_TTL_SECONDS`, `DAY1_CLUSTER_NAME_STRIP_PREFIX`;
- `DAY2_CACHE_TTL_SECONDS`, `DAY2_GITOPS_BRANCH`;
- `GITLAB_VERIFY_TLS`, `WINGMAN_ENVIRONMENT`.

In `wingman-secrets`, `GITLAB_ACCESS_TOKEN` becomes `GITLAB_TOKEN`.
**STOP** on any other difference you can't explain.

Then:

```bash
helm upgrade <release> "$CHART" -n <ns> -f new-values.yaml <--set for secrets> --wait --timeout 10m
kubectl -n <ns> rollout status deploy --timeout=5m
```

If a pod doesn't become ready, read why before anything else:

```bash
kubectl -n <ns> logs deploy/<name>                 # a missing or invalid setting is named at startup
kubectl -n <ns> port-forward deploy/<name> 18001:<port> &   # 8001 day1, 8002 day2
curl -s localhost:18001/health/ready               # which readiness check fails, and why
```

A settings error means the values file is wrong (step 5). A GitLab failure
in `/health/ready` means the token or TLS is wrong (checks 4.1, 5). Fix it,
or roll back (step 9). Don't change code.

## 8. Verify

Sign in, as an admin and as a viewer, and check each page reads:

| Page | Expected |
|---|---|
| Clusters | Every file under `hostedClusters/` is listed. Count them in GitLab and compare. Off-convention names are flagged, never hidden. |
| A cluster | Its values, its HostedCluster (if live status is on), its Drift tab |
| Specs | Every spec loads, or shows why it doesn't |
| New cluster | Fill the form for an existing site and MCE and press **Preview**, not Create. The preview must render and pass every check. |
| Addons | Every team repo's add-ons and fleet defaults; a cluster's Addons tab lists its charts |
| Approvals | Open MRs, including those from the old version |
| Audit | Both tabs load |

And the services themselves, through a port-forward (the images carry no
shell tools to rely on):

```bash
kubectl -n <ns> port-forward deploy/<day1 deployment> 18001:8001 &
kubectl -n <ns> port-forward deploy/<day2 deployment> 18002:8002 &
curl -s localhost:18001/health/ready; curl -s localhost:18002/health/ready
curl -s localhost:18001/metrics | grep wingman_build_info   # the version and commit you deployed
```

Don't create, edit or delete a real cluster to test.

## 9. Roll back

Wingman keeps no state, so going back is:

```bash
helm rollback <release> <previous revision> -n <ns> --wait
```

If step 6 changed `cluster-template.j2`, revert that MR, because the old
services expect the old template. MRs the new version opened use the same
formats, so the old version still lists them.

## 10. Report

Hand back:
- what ran before and after (image tags, chart revisions);
- `manifest.diff` with Secret data removed;
- the result of every check in section 4, with the STOP reason if one was hit;
- the MRs you opened;
- anything a page showed as an error.

Never include `current-values.yaml` or any secret.

## Known limits after this upgrade

- **Deleting a cluster doesn't release its network segment.** The planned
  delete-cluster workflow will, as the day1 workflow will allocate it
  (`docs/ideas/architecture-fit.md`).
- **Live status** (`clusterStatus.enabled`) needs the MCE service-account
  tokens Secret, as before. Off, the pages show a dash, not an error.
