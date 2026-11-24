// A new KV cluster on a seed (ADR-0069): `GET /api/day1/seeds/{seed}/kv-cluster-draft`
// and `POST /api/day1/seeds/{seed}/kv-clusters` (kv_clusters_schemas.py). Admins only.

/** The KV cluster a new one copies its owner, configs and tuning profiles from. */
export interface KvModel {
  name: string;
  site: string;
  seed: string;
  configs: string[];
  /** Its first NodePool's `tuningConfig`: one profile, several, or none. */
  tuning_config: string | string[] | null;
}

/** The new KV cluster's file as Wingman fills it, and why it cannot be created yet. */
export interface KvDraft {
  seed: string;
  site: string;
  /** `ocp4-<lc>-kv-<site>-<zone>-<id>`, the lowest free id; `null` with `problems`. */
  name: string | null;
  zone: string | null;
  /** The seed name's zone, or the zones of its bare-metal InfraEnvs when its name gives none. */
  zones: string[];
  mastertag: string | null;
  /** The releases the seed offers, newest first, its default spelled as its values.yaml does. */
  versions: string[];
  infra_env: string | null;
  /** The zone's bare-metal InfraEnvs (`<flavor>-mtl-<zone>`) to choose from. */
  infra_envs: string[];
  /** `hub`: read live; `files`: what the seed's KV clusters name (live status off). */
  infra_envs_from: "hub" | "files";
  workers: number;
  default_workers: number;
  max_workers: number;
  /** The capacity policy's `standbyWorkers` range, `[1, 5]`. */
  standby_workers: [number, number];
  /** `null` when no KV cluster exists: the owner is then the request's, and no configs. */
  model: KvModel | null;
  owner: Record<string, string>;
  path: string | null;
  /** The file provision-cluster gets; `null` while `problems` say why not. */
  yaml: string | null;
  problems: string[];
}

/** What the dialog chose; anything left out is the draft's own pick. */
export interface KvChoices {
  zone?: string | null;
  infra_env?: string | null;
  mastertag?: string | null;
  workers?: number;
  /** Only read when no KV cluster exists to copy the owner from. */
  owner?: { merkaz: string; anaf: string; mador: string } | null;
}

/** `POST /seeds/{seed}/kv-clusters`: the choices and the name the draft showed (another is a 409). */
export interface CreateKvCluster extends KvChoices {
  name: string;
}
