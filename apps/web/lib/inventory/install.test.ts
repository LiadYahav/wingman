import { describe, expect, it } from "vitest";
import type { InventoryRun, MceInventory, PoolCount } from "@/types/inventory";
import {
  OTHER_INFRA_ENV,
  chosenInfraEnv,
  drawableIn,
  infraEnvOptions,
  infraEnvProblem,
  knownInfraEnvs,
  mceOptions,
} from "./install";

const pool = (infraEnv: string | null, overrides: Partial<PoolCount> = {}): PoolCount => ({
  infra_env: infraEnv, available: 1, usable: 1, hardware: [], drawable: infraEnv ? 2 : null, ...overrides,
});

const mce = (name: string, overrides: Partial<MceInventory> = {}): MceInventory => ({
  site: "site1", mce: name, known: true, servers: 3, in_clusters: 1, available: 2, usable: 2,
  pools: [], infra_envs: [], infra_envs_error: null, infra_envs_from: "mce", ...overrides,
});

const run = (mceName: string, infraEnv: string | null): InventoryRun => ({
  workflow_id: `add-server-to-mce-${mceName}_${infraEnv}_1`, status: "running", started_at: null, closed_at: null,
  mce: mceName, infra_env: infraEnv, slot: 1, server_name: null, origin: "pool", phase: null, error: null,
});

describe("an InfraEnv name", () => {
  it("is a DNS label, as day1 and Kubernetes require", () => {
    expect(infraEnvProblem("dell-r650-site1-96c-768gb")).toBeNull();
    expect(infraEnvProblem("a")).toBeNull();
    expect(infraEnvProblem("")).toMatch(/Give/);
    for (const bad of ["Dell-R650", "dell_r650", "-dell", "dell-", "dell r650"]) {
      expect(infraEnvProblem(bad), bad).toMatch(/Lowercase letters/);
    }
    expect(infraEnvProblem("a".repeat(63))).toBeNull();
    expect(infraEnvProblem("a".repeat(64))).toMatch(/63/);
  });

  it("is the picked one, or the typed one once it is a label", () => {
    expect(chosenInfraEnv(null, "anything")).toBeNull();
    expect(chosenInfraEnv("dell-r650", "")).toBe("dell-r650");
    expect(chosenInfraEnv(OTHER_INFRA_ENV, "  cisco-m6  ")).toBe("cisco-m6");
    expect(chosenInfraEnv(OTHER_INFRA_ENV, "Cisco_M6")).toBeNull();
    expect(chosenInfraEnv(OTHER_INFRA_ENV, "")).toBeNull();
  });
});

describe("the InfraEnvs the page knows", () => {
  it("are an MCE's pools and those its own pool draws filled, once each, by name", () => {
    const site1a = mce("a", { pools: [pool("r760"), pool(null), pool("hp")] });
    const runs = [run("a", "r650"), run("a", "hp"), run("b", "other"), run("a", null)];
    expect(knownInfraEnvs(site1a, runs)).toEqual(["hp", "r650", "r760"]);
    expect(knownInfraEnvs(undefined, runs)).toEqual([]);
  });

  it("offer each with its count, a run's with where it was seen, then another one to type", () => {
    const site1a = mce("a", { pools: [pool("r760", { available: 4 })] });
    const options = infraEnvOptions(["r650", "r760"], site1a);
    expect(options.map((o) => [o.value, o.description])).toEqual([
      ["r650", "seen in the runs"],
      ["r760", "4 available"],
      [OTHER_INFRA_ENV, "Type its name"],
    ]);
  });

  it("say what a pool draw could pick only for a pool server-scan counts", () => {
    const site1a = mce("a", { pools: [pool("r760", { drawable: 3 })] });
    expect(drawableIn(site1a, "r760")).toBe(3);
    expect(drawableIn(site1a, "typed")).toBeNull();
    expect(drawableIn(undefined, "r760")).toBeNull();
    expect(drawableIn(site1a, null)).toBeNull();
  });
});

describe("the MCE picker", () => {
  it("groups the day1 MCEs by site and says what server-scan knows of each", () => {
    const options = mceOptions([mce("a"), mce("c", { site: "site2", known: false })]);
    expect(options).toEqual([
      { value: "a", label: "a", group: "site1", description: "2 available" },
      { value: "c", label: "c", group: "site2", description: "not in server-scan" },
    ]);
  });
});
