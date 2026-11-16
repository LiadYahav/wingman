import { describe, expect, it } from "vitest";
import type { TuningProfiles } from "@/types";
import { CONFIGS_RULE, addNodepool, configsMode, newDraft, type FlavorDraft } from "./model";
import { chooseConfigsMode, isTuningRule, poolTuning, setPoolTuning, setTuningRule, tuningAgrees, tuningIssues } from "./tuning-model";

const RULE = "nodepools[*].tuning_config";
const DEFAULTS = [{ name: "nm-conf", hardware: "generic" }, { name: "workers-chrony-configuration" }];
const CATALOG: TuningProfiles = {
  folder: "tuning",
  found: true,
  profiles: [
    { name: "tuned-a", kind: "Tuned", summary: null, path: "tuning/tuned-a.yaml", clusters: [], requires_performance_profile: null },
    { name: "tuned-b", kind: "Tuned", summary: null, path: "tuning/tuned-b.yaml", clusters: [], requires_performance_profile: null },
  ],
  problems: [],
};

/** A new flavor of `pools` nodepools, each with its own profiles. */
function draftOf(...pools: string[][]): FlavorDraft {
  let draft = newDraft(DEFAULTS);
  for (let i = 1; i < pools.length; i++) draft = addNodepool(draft, DEFAULTS, "generic");
  return pools.reduce((d, names, i) => setPoolTuning(d, i, names), draft);
}

const toRule = (draft: FlavorDraft, offered = true) => chooseConfigsMode(draft, "rule", DEFAULTS, "generic", offered);
const toEach = (draft: FlavorDraft) => chooseConfigsMode(draft, "each", DEFAULTS, "generic", true);
const tuning = (draft: FlavorDraft) => draft.keys.map((_, i) => poolTuning(draft, i));

describe("tuning profiles in the every-nodepool panel", () => {
  it("includes Nodepool 1's profiles when the nodepools agree, as a set", () => {
    const draft = toRule(draftOf(["tuned-a", "tuned-b"], ["tuned-b", "tuned-a"]));
    expect(configsMode(draft)).toBe("rule");
    expect(draft.locked).toEqual([CONFIGS_RULE, RULE]);
    expect(tuning(draft)).toEqual([["tuned-a", "tuned-b"], ["tuned-a", "tuned-b"]]);
  });

  it("leaves the tuning alone when the nodepools differ, or tuning/ offers nothing", () => {
    const differ = draftOf(["tuned-a"], ["tuned-b"]);
    expect(tuningAgrees(differ)).toBe(false);
    const ruled = toRule(differ);
    expect(isTuningRule(ruled)).toBe(false);
    expect(tuning(ruled)).toEqual([["tuned-a"], ["tuned-b"]]);
    expect(isTuningRule(toRule(draftOf(["tuned-a"]), false))).toBe(false);
  });

  it("turns the rule on with no names yet, which a save refuses at the panel", () => {
    const draft = toRule(draftOf([], []));
    expect(isTuningRule(draft)).toBe(true);
    expect(tuningIssues(draft, CATALOG)).toEqual([
      { path: RULE, message: "Choose the profiles every nodepool gets, or turn off the same tuning profiles" },
    ]);
  });

  it("checks the rule's names once, at the panel; per nodepool otherwise", () => {
    const panel = toRule(draftOf(["tuned-x"], ["tuned-x"]));
    expect(tuningIssues(panel, CATALOG)).toEqual([{ path: RULE, message: "tuned-x is not a tuning profile in tuning/" }]);
    const each = setTuningRule(draftOf(["tuned-x"], ["tuned-x"]), true, 0);
    expect(tuningIssues(each, CATALOG).map((i) => i.path)).toEqual(["nodepools[0].tuning_config", "nodepools[1].tuning_config"]);
    expect(tuningIssues(setTuningRule(draftOf([]), true, 0), CATALOG)).toEqual([
      { path: RULE, message: "Choose at least one profile to lock, or make the tuning profiles a preset" },
    ]);
  });

  it("drops both rules for each nodepool its own, every nodepool keeping its names", () => {
    const draft = toEach(toRule(draftOf(["tuned-a"], ["tuned-a"])));
    expect(draft.locked).toEqual([]);
    expect(tuning(draft)).toEqual([["tuned-a"], ["tuned-a"]]);
  });

  it("keeps a tuning rule locked per nodepool (3.37.0) until the mode really changes", () => {
    const locked = setTuningRule(draftOf(["tuned-a"], ["tuned-b"]), true, 0);
    expect(toEach(locked)).toBe(locked);
    const ruled = toRule(locked);
    expect(ruled.locked).toEqual([RULE, CONFIGS_RULE]);
    expect(tuning(ruled)).toEqual([["tuned-a"], ["tuned-a"]]);
  });
});
