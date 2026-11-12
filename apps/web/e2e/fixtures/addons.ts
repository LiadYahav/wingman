import type { ClusterSpec } from "../../types";
import type { CatalogEntry } from "../../types/day2";

type Chart = Pick<CatalogEntry, "team" | "name" | "current_version" | "available_versions" | "default_values"> &
  Partial<CatalogEntry>;

/** A catalog entry as `GET /api/day2/addons` returns it, from the fields a test cares about. */
export function catalogEntry({ team, name, ...rest }: Chart): CatalogEntry {
  return {
    team,
    name,
    argocd_metadata: {
      projectNamespace: name,
      repourl: `https://gitlab.example.com/helm-charts/${name}.git`,
      targetRevision: rest.current_version,
      syncPolicy: { syncOptions: ["CreateNamespace=true"] },
      path: ".",
    },
    dependencies: [],
    ocp_version_pins: [],
    fleet_defaults: [],
    chart_project: `helm-charts/${name}`,
    warnings: [],
    writable: true,
    read_only_reason: null,
    sync: { auto_sync: false, prune: false, self_heal: false, sync_options: ["CreateNamespace=true"] },
    ignore_differences: null,
    deploy_config_exists: true,
    last_commit_id: `${team}-catalog-1`,
    ...rest,
  };
}

// Typed against the app's API types so a shape change fails `tsc` instead of
// silently crashing the page-object tests at runtime.
export const mockAddons: CatalogEntry[] = [
  catalogEntry({
    team: "platform",
    name: "cert-manager",
    current_version: "1.12.0",
    available_versions: ["1.12.0", "1.11.0"],
    default_values: {
      replicas: 1,
      namespace: "cert-manager",
      installCRDs: true,
      resources: {
        requests: { cpu: "100m", memory: "128Mi" },
        limits: { cpu: "500m", memory: "512Mi" },
      },
    },
  }),
  catalogEntry({
    team: "platform",
    name: "external-secrets",
    current_version: "0.9.0",
    available_versions: ["0.9.0"],
    default_values: {
      replicaCount: 1,
      serviceAccount: { create: true, name: "" },
      secretStores: [],
    },
    fleet_defaults: ["hosted-clusters"],
  }),
  catalogEntry({
    team: "observability",
    name: "prometheus",
    current_version: "2.45.0",
    available_versions: ["2.45.0", "2.44.0"],
    default_values: {
      retention: "15d",
      scrapeInterval: "30s",
      alertmanager: { enabled: true },
      nodeExporter: { enabled: true },
    },
    ocp_version_pins: [{ version: "4.18.22", target_revision: "2.44.0" }],
  }),
  catalogEntry({
    team: "observability",
    name: "grafana",
    current_version: "10.0.0",
    available_versions: ["10.0.0"],
    default_values: {
      adminPassword: "",
      persistence: { enabled: false, size: "10Gi" },
      dashboards: [],
    },
    fleet_defaults: ["hosted-clusters"],
  }),
  catalogEntry({
    team: "networking",
    name: "ingress-nginx",
    current_version: "4.7.0",
    available_versions: ["4.7.0"],
    default_values: {
      controller: {
        replicaCount: 2,
        service: { type: "LoadBalancer" },
        resources: { requests: { cpu: "100m", memory: "90Mi" } },
      },
    },
  }),
];

export const mockSpecs: ClusterSpec[] = [
  {
    apiVersion: "wingman.io/v1",
    kind: "ClusterSpec",
    metadata: {
      name: "production-standard",
      version: "1.0.0",
      description: "Standard production cluster template",
      labels: {},
    },
    spec: {
      day1: {
        variables: [],
        structure: { nodepools_count: 2 },
        locked_paths: ["cluster_name"],
        template: "",
      },
      day2: {
        addons: [
          {
            team: "platform",
            name: "cert-manager",
            version: "1.12.0",
            overrideable: [
              { path: "replicas", type: "integer", default: 1, description: "Number of replicas" },
            ],
          },
        ],
      },
    },
  },
];
