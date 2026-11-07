import type { AddonCatalogEntry, ClusterSpec } from "../../types";

// Typed against the app's API types so a shape change fails `tsc` instead of
// silently crashing the page-object tests at runtime.
export const mockAddons: AddonCatalogEntry[] = [
  {
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
    dependencies: [],
  },
  {
    team: "platform",
    name: "external-secrets",
    current_version: "0.9.0",
    available_versions: ["0.9.0"],
    default_values: {
      replicaCount: 1,
      serviceAccount: { create: true, name: "" },
      secretStores: [],
    },
    dependencies: ["platform/cert-manager"],
  },
  {
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
    dependencies: [],
  },
  {
    team: "observability",
    name: "grafana",
    current_version: "10.0.0",
    available_versions: ["10.0.0"],
    default_values: {
      adminPassword: "",
      persistence: { enabled: false, size: "10Gi" },
      dashboards: [],
    },
    dependencies: [],
  },
  {
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
    dependencies: [],
  },
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
        immutable_paths: ["cluster_name"],
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
