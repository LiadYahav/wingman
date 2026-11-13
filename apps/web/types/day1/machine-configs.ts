// ── Machine configs (§1, §3, ADR-0027) ──────────────────────────────────────

/**
 * A nodepool's `configs` entry: a static config by name, or the cluster's own
 * network config `{name: "nm-conf", hardware}`, which day1 writes to the file
 * as `nm-conf-<clusterName>-<hardware>`. `hardware` belongs only to `nm-conf`.
 */
export interface ConfigEntry {
  name: string;
  hardware?: string | null;
}

/** A file under `mc-files/` (never `legacy/`); `folder` is `""` for the root. */
export interface StaticConfig {
  name: string;
  folder: string;
  path: string;
}

/** A network template `mc-files/templates/nm-conf-template-<name>.bu`, or the generic `nm-conf-template.bu`. */
export interface HardwareType {
  name: string;
  template: string;
  /** `generic`: for any hardware, written as plain `nm-conf`; listed first. */
  generic: boolean;
}

/** The specs repo's `nodepool-defaults.yaml`: the configs a new nodepool starts with. */
export interface NodepoolDefaults {
  path: string;
  /** `false`: there is no such file; no defaults, not an error. */
  found: boolean;
  /** `nm-conf` may leave out its hardware: the nodepool picks it. */
  configs: ConfigEntry[];
  /** Set when the file exists but cannot be used; `configs` is then empty. */
  error: string | null;
  /** Why some default entries would not resolve, or why the file is unusable. */
  problems: string[];
}

/** `GET /api/day1/machine-configs` (any session). */
export interface MachineConfigs {
  /** Always `"nm-conf"`. */
  network_config: string;
  static_configs: StaticConfig[];
  hardware_types: HardwareType[];
  nodepool_defaults: NodepoolDefaults;
  /** Files in `mc-files/` that are not offered, and why (for admins). */
  problems: string[];
}
