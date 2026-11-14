import { describe, expect, it } from "vitest";
import type { DriftSummaryItem } from "@/types";
import { driftCounts, healthCounts } from "./health";

const drift = (state: DriftSummaryItem["state"], update: DriftSummaryItem["update"] = null): DriftSummaryItem => ({
  name: "c", site: "site1", mce: "m", spec_name: "f", spec_version: "1.0.0", state, is_drifted: null, error: null, update,
});

describe("the cluster health counts", () => {
  it("count each phase, a cluster with no live status as unknown", () => {
    expect(healthCounts(6, ["Ready", "Ready", "Provisioning", "Error", "Unknown"])).toEqual({
      ready: 2, provisioning: 1, error: 1, unknown: 2,
    });
  });

  it("are all unknown before any status", () => {
    expect(healthCounts(3, [])).toEqual({ ready: 0, provisioning: 0, error: 0, unknown: 3 });
  });
});

describe("the drift counts", () => {
  it("count the drifted, and say what else the summary knows", () => {
    const update = { version: "1.1.0" } as unknown as DriftSummaryItem["update"];
    const counts = driftCounts([drift("drifted"), drift("drifted"), drift("unknown"), drift("in_sync", update), drift("in_sync")]);
    expect(counts).toEqual({ drifted: 2, hint: "1 unknown · 1 with an update" });
  });

  it("say nothing before the summary is read", () => {
    expect(driftCounts(undefined)).toEqual({ drifted: 0, hint: "" });
  });
});
