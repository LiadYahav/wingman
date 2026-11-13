import { describe, expect, it } from "vitest";
import { dismissKey, isDismissed, readDismissed, runFingerprint, writeDismissed } from "@/lib/upgrade-dismiss";
import type { UpgradeRun } from "@/types";

const finished = (overrides: Partial<UpgradeRun> = {}): UpgradeRun => ({
  workflow_id: "upgrade-cluster-ocp4-prod-lark-site1", cluster: "ocp4-prod-lark-site1", status: "completed",
  phase: null, waiting_for: null, mce: null, plan: null, profile: null, current_step: null, current_nodepool: null,
  nodepools_done: [], control_plane_version: "4.18.56", nodepool_versions: {}, max_unavailable: {}, paused: false,
  pending_actions: [], last_verdict: null, verified_against_graph: null,
  log: [{ at: "2026-11-13T11:00:00Z", event: "done", by: null, detail: "" }],
  outcome: "done", steps_completed: 2, error: null, decisions: null,
  ...overrides,
});

function memory(): Storage {
  const items = new Map<string, string>();
  return {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
  } as Storage;
}

describe("dismissing a finished upgrade", () => {
  it("hides that run only: the cluster's next run under the same id shows again", () => {
    const storage = memory();
    expect(writeDismissed(storage, finished())).toBe(true);
    const stored = readDismissed(storage, finished().workflow_id);
    expect(isDismissed(finished(), stored)).toBe(true);
    const next = finished({ log: [{ at: "2026-11-14T09:00:00Z", event: "done", by: null, detail: "" }] });
    expect(isDismissed(next, stored)).toBe(false);
    expect(isDismissed(finished({ status: "running", outcome: null }), stored)).toBe(false);
  });

  it("tells runs apart by outcome too, and keeps one entry per cluster", () => {
    expect(runFingerprint(finished())).not.toBe(runFingerprint(finished({ outcome: "aborted" })));
    expect(dismissKey("upgrade-cluster-x")).toBe("wingman.upgrade-dismissed.upgrade-cluster-x");
  });

  it("without storage nothing is kept and nothing throws", () => {
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } } as unknown as Storage;
    expect(readDismissed(broken, "upgrade-cluster-x")).toBeNull();
    expect(writeDismissed(broken, finished())).toBe(false);
    expect(readDismissed(undefined, "upgrade-cluster-x")).toBeNull();
    expect(writeDismissed(undefined, finished())).toBe(false);
  });
});
