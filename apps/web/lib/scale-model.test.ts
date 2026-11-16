import { describe, expect, it } from "vitest";
import {
  busyReason,
  currentOf,
  directionOf,
  kindBlock,
  needsRestore,
  nodepoolBlock,
  phaseWords,
  replicasOf,
  startBody,
  stateWord,
} from "./scale-model";
import type { ScaleKind, ScaleNodePool, ScaleRun } from "@/types";

const run = (overrides: Partial<ScaleRun> = {}): ScaleRun => ({
  workflow_id: "update-nodepool-ocp4-prod-lark-site1",
  status: "running",
  phase: "scaling-down",
  direction: "down",
  child: null,
  result: null,
  error: null,
  error_type: null,
  ...overrides,
});

const pool = (overrides: Partial<ScaleNodePool> = {}): ScaleNodePool => ({
  index: 0,
  name: "prod-lark-site1-dell-r660",
  infra_env: "dell-r660",
  replicas: 3,
  locked_by: null,
  locked_replicas: null,
  unnamed: null,
  ...overrides,
});

const kind = (overrides: Partial<ScaleKind> = {}): ScaleKind => ({
  kind: "dell-r660",
  nodepools: ["prod-lark-site1-dell-r660"],
  total: 3,
  locked: [],
  ...overrides,
});

describe("phaseWords", () => {
  it("humanizes the workflow's phase, and its child's while the child has one", () => {
    expect(phaseWords(run({ child: null }))).toBe("Scaling down");
    const child = { workflow_id: "scale-down-nodepool-x", status: "running", phase: "marking-machines", error: null };
    expect(phaseWords(run({ child }))).toBe("Scaling down · Marking machines");
  });

  it("shows a phase it has never seen in words, and Starting before the first", () => {
    expect(phaseWords(run({ phase: "waiting-for-quorum" }))).toBe("Waiting for quorum");
    expect(phaseWords(run({ phase: null }))).toBe("Starting");
  });

  it("drops a child that completed", () => {
    const child = { workflow_id: "scale-up-nodepool-x", status: "completed", phase: "completed", error: null };
    expect(phaseWords(run({ phase: "scaling-up", child }))).toBe("Scaling up");
  });
});

describe("stateWord", () => {
  it("is the phase while it runs, the status once it closed", () => {
    expect(stateWord(run({ phase: "planning" }))).toBe("Planning");
    expect(stateWord(run({ status: "failed", phase: "planning" }))).toBe("Failed");
    expect(stateWord(run({ status: "timed_out" }))).toBe("Timed out");
  });
});

describe("busyReason", () => {
  it("waits for a scale run first, then an open upgrade, else nothing", () => {
    expect(busyReason(true, true)).toMatch(/update-nodepool run of this cluster is running/);
    expect(busyReason(false, true)).toMatch(/upgrade-cluster run of this cluster is open/);
    expect(busyReason(false, false)).toBeNull();
  });
});

describe("what can be scaled", () => {
  it("refuses a kind that selects a locked NodePool, naming the flavor and the pools", () => {
    expect(kindBlock(kind(), "agent-standard")).toBeNull();
    expect(kindBlock(kind({ locked: ["a", "b"] }), "agent-standard")).toBe(
      "Locked by flavor agent-standard: it selects a, b, whose replicas the flavor fixes."
    );
    expect(kindBlock(kind({ total: null }), null)).toMatch(/not a number/);
  });

  it("refuses an unnamed or a locked NodePool by name", () => {
    expect(nodepoolBlock(pool())).toBeNull();
    expect(nodepoolBlock(pool({ name: null, unnamed: "nodepool[2] has neither name nor infraEnvName" }))).toBe(
      "nodepool[2] has neither name nor infraEnvName"
    );
    expect(nodepoolBlock(pool({ locked_by: "agent-standard", locked_replicas: 5 }))).toBe("Locked by flavor agent-standard at 5.");
  });

  it("offers a restore only for a named, locked NodePool whose replicas differ", () => {
    expect(needsRestore(pool({ locked_by: "f", locked_replicas: 5 }))).toBe(true);
    expect(needsRestore(pool({ locked_by: "f", locked_replicas: 3 }))).toBe(false);
    expect(needsRestore(pool({ locked_by: "f", locked_replicas: 5, name: null }))).toBe(false);
    expect(needsRestore(pool())).toBe(false);
  });
});

describe("the start", () => {
  it("sends exactly one target", () => {
    expect(startBody("kind", "dell-r660", 12)).toEqual({ infra_env_kind: "dell-r660", replicas: 12 });
    expect(startBody("nodepool", "prod-lark-site1-dell-r660", 0)).toEqual({ nodepool: "prod-lark-site1-dell-r660", replicas: 0 });
  });

  it("waits for a target and a whole number from 0", () => {
    expect(startBody("kind", null, 3)).toBeNull();
    expect(startBody("kind", "k", NaN)).toBeNull();
    expect(startBody("kind", "k", -1)).toBeNull();
    expect(startBody("kind", "k", 2.5)).toBeNull();
    expect(replicasOf(501)).toBeNull();
  });

  it("knows where the choice is now and which way it goes, never the plan", () => {
    const kinds = [kind({ total: 9 })];
    const pools = [pool({ replicas: 3 })];
    expect(currentOf("kind", "dell-r660", kinds, pools)).toBe(9);
    expect(currentOf("nodepool", "prod-lark-site1-dell-r660", kinds, pools)).toBe(3);
    expect(currentOf("kind", null, kinds, pools)).toBeNull();
    expect(directionOf(9, 12)).toBe("up");
    expect(directionOf(9, 8)).toBe("down");
    expect(directionOf(9, 9)).toBe("none");
    expect(directionOf(null, 9)).toBeNull();
  });
});
