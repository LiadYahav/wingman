#!/usr/bin/env python3
"""
Seed GitLab with test data for local Wingman development.

Creates the correct group/project structure:
  wingman-dev/           ← top-level group
    day1-config          ← project: cluster HCPs + NodePools
    cluster-specs        ← project: ClusterSpec templates
    charts/              ← subgroup: helm chart repos (version branches = available versions)
      cert-manager
      kube-prometheus-stack
      metallb
      nginx-ingress
    sigs/                ← subgroup: one project per team
      platform-sre       ← project: operators + mce overrides for SRE team
      network-team       ← project: operators + mce overrides for network team

Usage:
    python scripts/seed-test-data.py \\
        --gitlab-url http://localhost:8929 \\
        --token <root-token>
"""
from __future__ import annotations

import argparse
import sys
import textwrap
import time
from typing import Any

import gitlab
from gitlab.exceptions import GitlabGetError


# ── Cluster specs ──────────────────────────────────────────────────────────────

SPEC_STANDARD_HA = textwrap.dedent("""\
    apiVersion: wingman.io/v1
    kind: ClusterSpec
    metadata:
      name: standard-ha
      description: "Standard HA cluster with 3 workers — default for production workloads"
      version: "1.2.0"
      labels:
        tier: production
    spec:
      day1:
        variables:
          - name: cluster_name
            type: string
            required: true
            pattern: "^[a-z][a-z0-9-]{2,62}$"
            description: "Cluster name (lowercase, alphanumeric, hyphens)"
          - name: site_name
            type: string
            required: true
            description: "Datacenter site name"
          - name: mce_name
            type: string
            required: true
            description: "MCE (MultiClusterEngine) namespace"
          - name: worker_count
            type: integer
            default: 3
            minimum: 1
            maximum: 50
            description: "Number of worker nodes"
          - name: ocp_version
            type: string
            required: true
            enum: ["4.14.12", "4.15.3", "4.15.9", "4.16.0", "4.16.3"]
            description: "OpenShift version to deploy"
          - name: network_type
            type: string
            default: "OVNKubernetes"
            enum: ["OVNKubernetes", "OpenShiftSDN"]
            description: "Container network interface"
        template: |
          ---
          apiVersion: hypershift.openshift.io/v1beta1
          kind: HostedCluster
          metadata:
            name: {{ cluster_name }}
            namespace: {{ mce_name }}
          spec:
            release:
              image: quay.io/openshift-release-dev/ocp-release:{{ ocp_version }}-x86_64
            dns:
              baseDomain: apps.internal
            networking:
              networkType: {{ network_type }}
              clusterNetwork:
                - cidr: 10.132.0.0/14
              serviceNetwork:
                - cidr: 172.31.0.0/16
            platform:
              type: Agent
              agent:
                agentNamespace: {{ mce_name }}-agents
            pullSecret:
              name: pull-secret
          ---
          apiVersion: hypershift.openshift.io/v1beta1
          kind: NodePool
          metadata:
            name: {{ cluster_name }}-workers
            namespace: {{ mce_name }}
          spec:
            clusterName: {{ cluster_name }}
            replicas: {{ worker_count }}
            management:
              upgradeType: InPlace
            platform:
              type: Agent
      day2:
        addons:
          - team: platform-sre
            name: cert-manager
            version: "1.14.0"
            overrides: {}
          - team: platform-sre
            name: kube-prometheus-stack
            version: "57.2.0"
            overrides:
              prometheus.retention: "30d"
          - team: network-team
            name: metallb
            version: "0.14.5"
            overrides: {}
""")

SPEC_COMPACT = textwrap.dedent("""\
    apiVersion: wingman.io/v1
    kind: ClusterSpec
    metadata:
      name: compact-single
      description: "Compact single-node cluster for dev/test environments"
      version: "1.0.0"
      labels:
        tier: development
    spec:
      day1:
        variables:
          - name: cluster_name
            type: string
            required: true
          - name: site_name
            type: string
            required: true
          - name: mce_name
            type: string
            required: true
          - name: ocp_version
            type: string
            required: true
            enum: ["4.14.12", "4.15.3", "4.15.9", "4.16.0"]
        template: |
          ---
          apiVersion: hypershift.openshift.io/v1beta1
          kind: HostedCluster
          metadata:
            name: {{ cluster_name }}
            namespace: {{ mce_name }}
          spec:
            release:
              image: quay.io/openshift-release-dev/ocp-release:{{ ocp_version }}-x86_64
            platform:
              type: Agent
              agent:
                agentNamespace: {{ mce_name }}-agents
            pullSecret:
              name: pull-secret
          ---
          apiVersion: hypershift.openshift.io/v1beta1
          kind: NodePool
          metadata:
            name: {{ cluster_name }}-workers
            namespace: {{ mce_name }}
          spec:
            clusterName: {{ cluster_name }}
            replicas: 1
            platform:
              type: Agent
      day2:
        addons:
          - team: platform-sre
            name: cert-manager
            version: "1.14.0"
            overrides: {}
""")

# ── Day1 clusters ──────────────────────────────────────────────────────────────

CLUSTER_ALPHA_YAML = textwrap.dedent("""\
    ---
    apiVersion: hypershift.openshift.io/v1beta1
    kind: HostedCluster
    metadata:
      name: alpha
      namespace: mce-prod
    spec:
      release:
        image: quay.io/openshift-release-dev/ocp-release:4.15.3-x86_64
      dns:
        baseDomain: apps.internal
      networking:
        networkType: OVNKubernetes
        clusterNetwork:
          - cidr: 10.132.0.0/14
        serviceNetwork:
          - cidr: 172.31.0.0/16
      platform:
        type: Agent
        agent:
          agentNamespace: mce-prod-agents
      pullSecret:
        name: pull-secret
    ---
    apiVersion: hypershift.openshift.io/v1beta1
    kind: NodePool
    metadata:
      name: alpha-workers
      namespace: mce-prod
    spec:
      clusterName: alpha
      replicas: 3
      management:
        upgradeType: InPlace
      platform:
        type: Agent
""")

CLUSTER_ALPHA_WINGMAN = textwrap.dedent("""\
    specName: standard-ha
    specVersion: "1.2.0"
    createdBy: admin
    createdAt: "2026-03-15T09:00:00Z"
    site: dc1
    mce: mce-prod
    variables:
      cluster_name: alpha
      site_name: dc1
      mce_name: mce-prod
      worker_count: 3
      ocp_version: "4.15.3"
      network_type: OVNKubernetes
""")

CLUSTER_BETA_YAML = textwrap.dedent("""\
    ---
    apiVersion: hypershift.openshift.io/v1beta1
    kind: HostedCluster
    metadata:
      name: beta
      namespace: mce-prod
    spec:
      release:
        image: quay.io/openshift-release-dev/ocp-release:4.16.0-x86_64
      dns:
        baseDomain: apps.internal
      networking:
        networkType: OVNKubernetes
        clusterNetwork:
          - cidr: 10.132.0.0/14
        serviceNetwork:
          - cidr: 172.31.0.0/16
      platform:
        type: Agent
        agent:
          agentNamespace: mce-prod-agents
      pullSecret:
        name: pull-secret
    ---
    apiVersion: hypershift.openshift.io/v1beta1
    kind: NodePool
    metadata:
      name: beta-workers
      namespace: mce-prod
    spec:
      clusterName: beta
      replicas: 5
      management:
        upgradeType: InPlace
      platform:
        type: Agent
""")

CLUSTER_BETA_WINGMAN = textwrap.dedent("""\
    specName: standard-ha
    specVersion: "1.2.0"
    createdBy: platform-admin
    createdAt: "2026-04-02T14:30:00Z"
    site: dc1
    mce: mce-prod
    variables:
      cluster_name: beta
      site_name: dc1
      mce_name: mce-prod
      worker_count: 5
      ocp_version: "4.16.0"
      network_type: OVNKubernetes
""")

# ── Helm chart values (stored in chart repos at version branches) ──────────────

CERT_MANAGER_VALUES_1_12 = textwrap.dedent("""\
    # cert-manager helm chart defaults — v1.12.x
    installCRDs: true
    replicaCount: 1
    resources:
      requests:
        cpu: 10m
        memory: 32Mi
      limits:
        cpu: 100m
        memory: 128Mi
    prometheus:
      enabled: true
      servicemonitor:
        enabled: false
    webhook:
      replicaCount: 1
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
    cainjector:
      replicaCount: 1
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
    global:
      logLevel: 2
""")

CERT_MANAGER_VALUES_1_13 = textwrap.dedent("""\
    # cert-manager helm chart defaults — v1.13.x
    installCRDs: true
    replicaCount: 1
    resources:
      requests:
        cpu: 10m
        memory: 32Mi
      limits:
        cpu: 100m
        memory: 128Mi
    prometheus:
      enabled: true
      servicemonitor:
        enabled: true
    webhook:
      replicaCount: 1
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
    cainjector:
      replicaCount: 1
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
    global:
      logLevel: 2
    startupapicheck:
      enabled: true
""")

CERT_MANAGER_VALUES_1_14 = textwrap.dedent("""\
    # cert-manager helm chart defaults — v1.14.x
    installCRDs: true
    replicaCount: 1
    resources:
      requests:
        cpu: 10m
        memory: 32Mi
      limits:
        cpu: 100m
        memory: 128Mi
    prometheus:
      enabled: true
      servicemonitor:
        enabled: true
    webhook:
      replicaCount: 1
      timeoutSeconds: 30
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
    cainjector:
      replicaCount: 1
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
    global:
      logLevel: 2
    startupapicheck:
      enabled: true
      timeout: 5m
""")

PROMETHEUS_VALUES_55 = textwrap.dedent("""\
    # kube-prometheus-stack defaults — v55.x
    prometheus:
      retention: "7d"
      retentionSize: "10GB"
      replicas: 1
      resources:
        requests:
          cpu: 200m
          memory: 400Mi
    grafana:
      enabled: true
      replicas: 1
      adminPassword: admin
    alertmanager:
      enabled: true
      replicas: 1
    prometheusOperator:
      enabled: true
""")

PROMETHEUS_VALUES_57 = textwrap.dedent("""\
    # kube-prometheus-stack defaults — v57.x
    prometheus:
      retention: "7d"
      retentionSize: "10GB"
      replicas: 1
      resources:
        requests:
          cpu: 200m
          memory: 400Mi
      storageSpec:
        volumeClaimTemplate:
          spec:
            resources:
              requests:
                storage: 20Gi
    grafana:
      enabled: true
      replicas: 1
      adminPassword: admin
      persistence:
        enabled: false
    alertmanager:
      enabled: true
      replicas: 1
    prometheusOperator:
      enabled: true
      resources:
        requests:
          cpu: 100m
          memory: 128Mi
""")

METALLB_VALUES_013 = textwrap.dedent("""\
    # metallb defaults — v0.13.x
    controller:
      enabled: true
      replicas: 1
      resources:
        requests:
          cpu: 10m
          memory: 64Mi
    speaker:
      enabled: true
      resources:
        requests:
          cpu: 10m
          memory: 64Mi
    prometheus:
      serviceMonitor:
        enabled: false
""")

METALLB_VALUES_014 = textwrap.dedent("""\
    # metallb defaults — v0.14.x
    controller:
      enabled: true
      replicas: 1
      resources:
        requests:
          cpu: 10m
          memory: 64Mi
      logLevel: info
    speaker:
      enabled: true
      resources:
        requests:
          cpu: 10m
          memory: 64Mi
      logLevel: info
    prometheus:
      serviceMonitor:
        enabled: false
    rbac:
      create: true
""")

NGINX_VALUES_48 = textwrap.dedent("""\
    # nginx-ingress defaults — v4.8.x
    controller:
      replicaCount: 2
      resources:
        requests:
          cpu: 100m
          memory: 90Mi
        limits:
          cpu: 500m
          memory: 256Mi
      service:
        type: LoadBalancer
      metrics:
        enabled: false
      podAnnotations: {}
    defaultBackend:
      enabled: false
""")

NGINX_VALUES_410 = textwrap.dedent("""\
    # nginx-ingress defaults — v4.10.x
    controller:
      replicaCount: 2
      resources:
        requests:
          cpu: 100m
          memory: 90Mi
        limits:
          cpu: 500m
          memory: 256Mi
      service:
        type: LoadBalancer
        externalTrafficPolicy: Local
      metrics:
        enabled: true
        port: 10254
      podAnnotations: {}
      allowSnippetAnnotations: false
    defaultBackend:
      enabled: false
""")

# ── platform-sre team addon definitions ───────────────────────────────────────

# repourl points to the local GitLab chart repos (resolved at runtime by HelmValuesFetcher)
CERT_MANAGER_ARGOCD = """\
projectNamespace: openshift-cert-manager
repourl: {gitlab_url}/wingman-dev/charts/cert-manager
targetRevision: "1.14.0"
syncPolicy:
  automated:
    selfHeal: true
    prune: false
"""

CERT_MANAGER_TEAM_VALUES = textwrap.dedent("""\
    # platform-sre team defaults — applied on top of helm chart defaults
    installCRDs: true
    replicaCount: 1
    prometheus:
      enabled: true
      servicemonitor:
        enabled: true
    resources:
      requests:
        cpu: 20m
        memory: 64Mi
""")

PROMETHEUS_ARGOCD = """\
projectNamespace: openshift-monitoring
repourl: {gitlab_url}/wingman-dev/charts/kube-prometheus-stack
targetRevision: "57.2.0"
syncPolicy:
  automated:
    selfHeal: true
    prune: false
"""

PROMETHEUS_TEAM_VALUES = textwrap.dedent("""\
    # platform-sre team defaults for kube-prometheus-stack
    prometheus:
      retention: "14d"
      replicas: 1
    grafana:
      enabled: true
      adminPassword: changeme
    alertmanager:
      enabled: true
""")

# ── network-team addon definitions ─────────────────────────────────────────────

METALLB_ARGOCD = """\
projectNamespace: metallb-system
repourl: {gitlab_url}/wingman-dev/charts/metallb
targetRevision: "0.14.5"
syncPolicy:
  automated:
    selfHeal: true
    prune: false
"""

METALLB_TEAM_VALUES = textwrap.dedent("""\
    # network-team defaults for metallb
    controller:
      enabled: true
      replicas: 1
    speaker:
      enabled: true
    prometheus:
      serviceMonitor:
        enabled: false
    # Example of complex nested arrays (IP address pools)
    ipAddressPools:
      - name: production-pool
        protocol: layer2
        addresses:
          - 192.168.1.100-192.168.1.200
        autoAssign: true
      - name: staging-pool
        protocol: layer2
        addresses:
          - 192.168.2.50-192.168.2.100
        autoAssign: false
    # Network segments example (array of objects)
    networkSegments:
      - id: 1
        vlan: 100
        cidr: "10.0.1.0/24"
        gateway: "10.0.1.1"
      - id: 2
        vlan: 200
        cidr: "10.0.2.0/24"
        gateway: "10.0.2.1"
      - id: 3
        vlan: 300
        cidr: "10.0.3.0/24"
        gateway: "10.0.3.1"
""")

NGINX_ARGOCD = """\
projectNamespace: ingress-nginx
repourl: {gitlab_url}/wingman-dev/charts/nginx-ingress
targetRevision: "4.10.0"
syncPolicy:
  automated:
    selfHeal: true
    prune: false
"""

NGINX_TEAM_VALUES = textwrap.dedent("""\
    # network-team defaults for nginx-ingress
    controller:
      replicaCount: 2
      service:
        type: LoadBalancer
      metrics:
        enabled: true
""")

# ── Cluster override files ─────────────────────────────────────────────────────

# alpha cluster: cert-manager overrides (more resources for production)
CERT_MANAGER_ALPHA_OVERRIDE_ARGOCD = """\
projectNamespace: openshift-cert-manager
repourl: {gitlab_url}/wingman-dev/charts/cert-manager
targetRevision: "1.14.0"
syncPolicy:
  automated:
    selfHeal: true
    prune: false
"""

CERT_MANAGER_ALPHA_OVERRIDE_VALUES = textwrap.dedent("""\
    # alpha cluster overrides — production sizing
    replicaCount: 2
    resources:
      requests:
        cpu: 50m
        memory: 64Mi
      limits:
        cpu: 200m
        memory: 256Mi
    prometheus:
      enabled: true
      servicemonitor:
        enabled: true
""")

# alpha cluster: prometheus overrides (longer retention for prod)
PROMETHEUS_ALPHA_OVERRIDE_ARGOCD = """\
projectNamespace: openshift-monitoring
repourl: {gitlab_url}/wingman-dev/charts/kube-prometheus-stack
targetRevision: "57.2.0"
syncPolicy:
  automated:
    selfHeal: true
    prune: false
"""

PROMETHEUS_ALPHA_OVERRIDE_VALUES = textwrap.dedent("""\
    # alpha cluster overrides — extended retention for production
    prometheus:
      retention: "30d"
      retentionSize: "50GB"
      replicas: 2
    grafana:
      enabled: true
      replicas: 1
    alertmanager:
      enabled: true
      replicas: 2
""")


def wait_for_gitlab(gl: gitlab.Gitlab, retries: int = 30) -> None:
    print("Waiting for GitLab to be ready...")
    for i in range(retries):
        try:
            gl.auth()
            print("GitLab is ready.")
            return
        except Exception:
            print(f"  Not ready yet ({i+1}/{retries}), retrying in 10s...")
            time.sleep(10)
    print("ERROR: GitLab did not become ready in time.", file=sys.stderr)
    sys.exit(1)


def get_or_create_group(gl: gitlab.Gitlab, name: str, path: str, parent_id: int | None = None) -> Any:
    search_results = gl.groups.list(search=path)
    for g in search_results:
        if g.path == path:
            print(f"  Group '{path}' already exists (id={g.id})")
            return g
    payload: dict[str, Any] = {"name": name, "path": path, "visibility": "private"}
    if parent_id:
        payload["parent_id"] = parent_id
    group = gl.groups.create(payload)
    print(f"  Created group '{path}' (id={group.id})")
    return group


def get_or_create_project(gl: gitlab.Gitlab, name: str, path: str, namespace_id: int, full_path: str) -> Any:
    try:
        proj = gl.projects.get(full_path)
        print(f"  Project '{full_path}' already exists (id={proj.id})")
        return proj
    except GitlabGetError:
        proj = gl.projects.create({
            "name": name,
            "path": path,
            "namespace_id": namespace_id,
            "visibility": "private",
            "initialize_with_readme": True,
        })
        print(f"  Created project '{full_path}' (id={proj.id})")
        time.sleep(2)
        return proj


def upsert_file(project: Any, path: str, content: str, branch: str = "main") -> None:
    """Create or update a file in a project on a given branch."""
    try:
        f = project.files.get(file_path=path, ref=branch)
        f.content = content
        f.save(branch=branch, commit_message=f"seed: update {path}")
        print(f"    Updated {path}")
    except GitlabGetError:
        project.files.create({
            "file_path": path,
            "branch": branch,
            "content": content,
            "commit_message": f"seed: add {path}",
        })
        print(f"    Created {path}")


def ensure_branch(project: Any, branch: str, ref: str = "main") -> None:
    """Create branch if it doesn't exist."""
    try:
        project.branches.get(branch)
        print(f"    Branch '{branch}' already exists")
    except GitlabGetError:
        project.branches.create({"branch": branch, "ref": ref})
        print(f"    Created branch '{branch}'")
        time.sleep(1)


def seed_specs_repo(project: Any) -> None:
    print("\n  Seeding specs repo...")
    upsert_file(project, "specs/standard-ha.yaml", SPEC_STANDARD_HA)
    upsert_file(project, "specs/compact-single.yaml", SPEC_COMPACT)


def seed_day1_repo(project: Any) -> None:
    print("\n  Seeding day1 repo...")
    base = "sites/dc1/mces/mce-prod/hostedClusters"
    upsert_file(project, f"{base}/alpha.yaml", CLUSTER_ALPHA_YAML)
    upsert_file(project, f"{base}/alpha.wingman.yaml", CLUSTER_ALPHA_WINGMAN)
    upsert_file(project, f"{base}/beta.yaml", CLUSTER_BETA_YAML)
    upsert_file(project, f"{base}/beta.wingman.yaml", CLUSTER_BETA_WINGMAN)


def seed_chart_repo(project: Any, versions_and_values: list[tuple[str, str]]) -> None:
    """Seed a helm chart repo with version branches, each containing a values.yaml."""
    for version, values_content in versions_and_values:
        ensure_branch(project, version)
        upsert_file(project, "values.yaml", values_content, branch=version)


def seed_platform_sre_repo(project: Any, gitlab_url: str) -> None:
    print("\n  Seeding platform-sre team repo...")
    # Addon definitions (operators/)
    upsert_file(project, "operators/cert-manager/cert-manager.yaml",
                CERT_MANAGER_ARGOCD.format(gitlab_url=gitlab_url))
    upsert_file(project, "operators/cert-manager/values.yaml", CERT_MANAGER_TEAM_VALUES)

    upsert_file(project, "operators/kube-prometheus-stack/kube-prometheus-stack.yaml",
                PROMETHEUS_ARGOCD.format(gitlab_url=gitlab_url))
    upsert_file(project, "operators/kube-prometheus-stack/values.yaml", PROMETHEUS_TEAM_VALUES)

    # Cluster overrides for alpha: cert-manager + kube-prometheus-stack
    upsert_file(project, "mces/mce-prod/alpha/cert-manager/cert-manager.yaml",
                CERT_MANAGER_ALPHA_OVERRIDE_ARGOCD.format(gitlab_url=gitlab_url))
    upsert_file(project, "mces/mce-prod/alpha/cert-manager/values.yaml",
                CERT_MANAGER_ALPHA_OVERRIDE_VALUES)

    upsert_file(project, "mces/mce-prod/alpha/kube-prometheus-stack/kube-prometheus-stack.yaml",
                PROMETHEUS_ALPHA_OVERRIDE_ARGOCD.format(gitlab_url=gitlab_url))
    upsert_file(project, "mces/mce-prod/alpha/kube-prometheus-stack/values.yaml",
                PROMETHEUS_ALPHA_OVERRIDE_VALUES)


def seed_network_team_repo(project: Any, gitlab_url: str) -> None:
    print("\n  Seeding network-team repo...")
    upsert_file(project, "operators/metallb/metallb.yaml",
                METALLB_ARGOCD.format(gitlab_url=gitlab_url))
    upsert_file(project, "operators/metallb/values.yaml", METALLB_TEAM_VALUES)

    upsert_file(project, "operators/nginx-ingress/nginx-ingress.yaml",
                NGINX_ARGOCD.format(gitlab_url=gitlab_url))
    upsert_file(project, "operators/nginx-ingress/values.yaml", NGINX_TEAM_VALUES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Wingman test data into GitLab")
    parser.add_argument("--gitlab-url", default="http://localhost:8929", help="GitLab URL")
    parser.add_argument("--token", required=True, help="GitLab personal access token (admin)")
    parser.add_argument("--no-wait", action="store_true", help="Skip GitLab readiness wait")
    args = parser.parse_args()

    gl = gitlab.Gitlab(url=args.gitlab_url, private_token=args.token, ssl_verify=False)

    if not args.no_wait:
        wait_for_gitlab(gl)
    else:
        gl.auth()

    print("\n[1/6] Creating top-level group 'wingman-dev'...")
    root = get_or_create_group(gl, "Wingman Dev", "wingman-dev")

    print("\n[2/6] Creating flat projects (day1-config, cluster-specs)...")
    specs_proj = get_or_create_project(gl, "Cluster Specs", "cluster-specs", root.id, "wingman-dev/cluster-specs")
    day1_proj = get_or_create_project(gl, "Day1 Config", "day1-config", root.id, "wingman-dev/day1-config")

    print("\n[3/6] Creating charts subgroup + chart repos...")
    charts_group = get_or_create_group(gl, "Helm Charts", "charts", parent_id=root.id)
    cert_proj = get_or_create_project(gl, "cert-manager", "cert-manager", charts_group.id, "wingman-dev/charts/cert-manager")
    prom_proj = get_or_create_project(gl, "kube-prometheus-stack", "kube-prometheus-stack", charts_group.id, "wingman-dev/charts/kube-prometheus-stack")
    metallb_proj = get_or_create_project(gl, "metallb", "metallb", charts_group.id, "wingman-dev/charts/metallb")
    nginx_proj = get_or_create_project(gl, "nginx-ingress", "nginx-ingress", charts_group.id, "wingman-dev/charts/nginx-ingress")

    print("\n[4/6] Seeding chart repos with version branches...")
    print("  cert-manager chart:")
    seed_chart_repo(cert_proj, [
        ("1.12.0", CERT_MANAGER_VALUES_1_12),
        ("1.13.0", CERT_MANAGER_VALUES_1_13),
        ("1.14.0", CERT_MANAGER_VALUES_1_14),
    ])
    print("  kube-prometheus-stack chart:")
    seed_chart_repo(prom_proj, [
        ("55.5.0", PROMETHEUS_VALUES_55),
        ("57.2.0", PROMETHEUS_VALUES_57),
    ])
    print("  metallb chart:")
    seed_chart_repo(metallb_proj, [
        ("0.13.12", METALLB_VALUES_013),
        ("0.14.5", METALLB_VALUES_014),
    ])
    print("  nginx-ingress chart:")
    seed_chart_repo(nginx_proj, [
        ("4.8.3", NGINX_VALUES_48),
        ("4.10.0", NGINX_VALUES_410),
    ])

    print("\n[5/6] Creating sigs subgroup + team projects...")
    sigs_group = get_or_create_group(gl, "SIGs", "sigs", parent_id=root.id)
    sre_proj = get_or_create_project(gl, "Platform SRE", "platform-sre", sigs_group.id, "wingman-dev/sigs/platform-sre")
    net_proj = get_or_create_project(gl, "Network Team", "network-team", sigs_group.id, "wingman-dev/sigs/network-team")

    print("\n[6/6] Seeding all repos...")
    seed_specs_repo(specs_proj)
    seed_day1_repo(day1_proj)
    seed_platform_sre_repo(sre_proj, args.gitlab_url)
    seed_network_team_repo(net_proj, args.gitlab_url)

    print("\n✓ Done! Use these values in values.minikube.yaml:")
    print(f"  gitlab.day1ProjectId:    wingman-dev/day1-config    (id={day1_proj.id})")
    print(f"  gitlab.day2SigsGroupPath: wingman-dev/sigs")
    print(f"  gitlab.specsProjectId:   wingman-dev/cluster-specs   (id={specs_proj.id})")
    print("\n  Chart repos (for HelmValuesFetcher version listing):")
    print(f"    cert-manager:            wingman-dev/charts/cert-manager     versions: 1.12.0, 1.13.0, 1.14.0")
    print(f"    kube-prometheus-stack:   wingman-dev/charts/kube-prometheus-stack  versions: 55.5.0, 57.2.0")
    print(f"    metallb:                 wingman-dev/charts/metallb          versions: 0.13.12, 0.14.5")
    print(f"    nginx-ingress:           wingman-dev/charts/nginx-ingress    versions: 4.8.3, 4.10.0")


if __name__ == "__main__":
    main()
