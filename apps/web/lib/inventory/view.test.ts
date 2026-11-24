import { describe, expect, it } from "vitest";
import type { MceInventory } from "@/types/inventory";
import {
  cleanNames,
  inventoryHref,
  parseStoredView,
  readStoredView,
  resolveView,
  serializeView,
  viewFromSearch,
  withView,
  writeStoredView,
} from "./view";

const mce = (name: string, overrides: Partial<MceInventory> = {}): MceInventory => ({
  site: "site1", mce: name, known: true, servers: 3, in_clusters: 1, available: 2, usable: 2,
  pools: [], infra_envs: [], infra_envs_error: null, infra_envs_from: "mce", ready: 0, needs_fix: 0, total: 0,
  used: 0, used_error: null, unguarded: [], ...overrides,
});

const MCES = [mce("quiet", { known: false }), mce("a"), mce("b")];
const NOTHING = { mce: null, infraEnvs: [] };

describe("the view in the URL", () => {
  it("names the MCE and the InfraEnvs, comma-separated or repeated, each once in name order", () => {
    expect(viewFromSearch("?mce=a&infraEnv=c200-mtl-az2,c200-mtl-az1&infraEnv=c200-mtl-az1")).toEqual({
      mce: "a", infraEnvs: ["c200-mtl-az1", "c200-mtl-az2"],
    });
    expect(viewFromSearch("")).toEqual({ mce: null, infraEnvs: null });
    expect(viewFromSearch("?infraEnv=")).toEqual({ mce: null, infraEnvs: [] });
  });

  it("is written beside the URL's other parts, an empty choice left out", () => {
    const url = { pathname: "/inventory", search: "?x=1", hash: "#runs" };
    expect(withView(url, { mce: "a", infraEnvs: ["c200-mtl-az1", "r760-mtl-az1"] })).toBe(
      "/inventory?x=1&mce=a&infraEnv=c200-mtl-az1,r760-mtl-az1#runs"
    );
    expect(withView({ pathname: "/inventory", search: "?mce=a&infraEnv=x", hash: "" }, NOTHING)).toBe("/inventory");
    expect(inventoryHref("ocp4-prod-mce-site1-a")).toBe("/inventory?mce=ocp4-prod-mce-site1-a");
  });
});

describe("the view kept for the next visit", () => {
  it("round-trips, and anything of another shape is nothing", () => {
    const view = { mce: "a", infraEnvs: ["c200-mtl-az1"] };
    expect(parseStoredView(serializeView(view))).toEqual(view);
    for (const raw of [null, "", "not json", "[]", "null", '{"mce": 3, "infraEnvs": "x"}']) expect(parseStoredView(raw)).toEqual(NOTHING);
  });

  it("is read and written in try/catch: blocked storage keeps nothing", () => {
    const blocked = {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
    };
    expect(readStoredView(blocked)).toBeNull();
    expect(readStoredView(undefined)).toBeNull();
    expect(writeStoredView(blocked, "{}")).toBe(false);
    expect(writeStoredView(undefined, "{}")).toBe(false);
    const kept = new Map<string, string>();
    const storage = { getItem: (k: string) => kept.get(k) ?? null, setItem: (k: string, v: string) => void kept.set(k, v) };
    expect(writeStoredView(storage, "{}")).toBe(true);
    expect(readStoredView(storage)).toBe("{}");
  });

  it("holds names only, once each", () => {
    expect(cleanNames([" b ", "a", "b", "", 3, null])).toEqual(["a", "b"]);
  });
});

describe("the view shown", () => {
  it("opens on the first MCE with something to show, every InfraEnv", () => {
    expect(resolveView({ mce: null, infraEnvs: null }, NOTHING, MCES)).toEqual({ mce: MCES[1], infraEnvs: [], unknownMce: null });
  });

  it("takes the URL's MCE, else the remembered one, each part on its own", () => {
    const stored = { mce: "b", infraEnvs: ["c200-mtl-az1"] };
    expect(resolveView({ mce: null, infraEnvs: null }, stored, MCES)).toEqual({ mce: MCES[2], infraEnvs: ["c200-mtl-az1"], unknownMce: null });
    // A link to one MCE keeps the viewer's InfraEnvs; the URL's own InfraEnvs win
    expect(resolveView({ mce: "quiet", infraEnvs: null }, stored, MCES).infraEnvs).toEqual(["c200-mtl-az1"]);
    expect(resolveView({ mce: "quiet", infraEnvs: [] }, stored, MCES)).toEqual({ mce: MCES[0], infraEnvs: [], unknownMce: null });
  });

  it("falls back to the default for an unknown URL MCE, and says which", () => {
    expect(resolveView({ mce: "gone", infraEnvs: null }, { mce: "b", infraEnvs: [] }, MCES)).toEqual({
      mce: MCES[1], infraEnvs: [], unknownMce: "gone",
    });
    expect(resolveView({ mce: null, infraEnvs: null }, { mce: "gone", infraEnvs: [] }, MCES).unknownMce).toBeNull();
    expect(resolveView({ mce: "a", infraEnvs: null }, NOTHING, []).mce).toBeNull();
  });
});
