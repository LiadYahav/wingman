export const mockAddons = [
  {
    team: "platform",
    name: "cert-manager",
    description: "Certificate management for Kubernetes",
    version: "1.12.0",
    defaultValues: {
      replicas: 1,
      namespace: "cert-manager",
      installCRDs: true,
      resources: {
        requests: { cpu: "100m", memory: "128Mi" },
        limits: { cpu: "500m", memory: "512Mi" },
      },
    },
  },
  {
    team: "platform",
    name: "external-secrets",
    description: "External secrets operator",
    version: "0.9.0",
    defaultValues: {
      replicaCount: 1,
      serviceAccount: { create: true, name: "" },
      secretStores: [],
    },
  },
  {
    team: "observability",
    name: "prometheus",
    description: "Monitoring and alerting toolkit",
    version: "2.45.0",
    defaultValues: {
      retention: "15d",
      scrapeInterval: "30s",
      alertmanager: { enabled: true },
      nodeExporter: { enabled: true },
    },
  },
  {
    team: "observability",
    name: "grafana",
    description: "Visualization and analytics platform",
    version: "10.0.0",
    defaultValues: {
      adminPassword: "",
      persistence: { enabled: false, size: "10Gi" },
      dashboards: [],
    },
  },
  {
    team: "networking",
    name: "ingress-nginx",
    description: "NGINX Ingress Controller",
    version: "4.7.0",
    defaultValues: {
      controller: {
        replicaCount: 2,
        service: { type: "LoadBalancer" },
        resources: { requests: { cpu: "100m", memory: "90Mi" } },
      },
    },
  },
];

export const mockSpecs = [
  {
    name: "production-standard",
    displayName: "Production Standard",
    description: "Standard production cluster template",
    variables: [
      { name: "cluster_name", description: "Name of the cluster", required: true },
      { name: "environment", description: "Environment (prod/staging)", default: "prod" },
    ],
    day2Addons: [
      {
        team: "platform",
        name: "cert-manager",
        overrideable: [
          { path: "replicas", type: "integer", default: 1, description: "Number of replicas" },
        ],
      },
    ],
  },
];
