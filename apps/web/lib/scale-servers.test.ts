import { describe, expect, it } from "vitest";
import { pickedLeaving, pickedWords, picksReady, serversOf } from "./scale-servers";
import type { NodePoolNodes, PoolNode } from "@/types";

const node = (overrides: Partial<PoolNode>): PoolNode => ({
  machine: "pool-m0", node_name: "worker-0", state: "ready", current: false, activity: null, waiting_for: null, outdated: null,
  agent: null, server_name: null, server: null, machine_server: null, uninstall: null, ...overrides,
});

const pool = (nodes: PoolNode[]): NodePoolNodes => ({
  name: "pool", wanted: 3, autoscaling: null, ready: 3, version: "4.19.3", upgrade_type: "InPlace", agent_selector: null,
  update: null, problems: [], free_agents: null, nodes,
});

describe("the servers a scale-down can pick", () => {
  it("are the NodePool's Machines, named by the workflow's rule and shown by server-scan's name", () => {
    const servers = serversOf(
      pool([
        node({ machine: "pool-a", server_name: "ocp-r660-DL01", machine_server: "ocp-r660-dl01" }),
        node({ machine: "pool-b", server_name: null, machine_server: "worker-7", node_name: "worker-7", state: "not_ready" }),
        node({ machine: "pool-c", machine_server: null, node_name: null, state: "waiting" }),
        node({ machine: "pool-d", server_name: "ocp-r660-DL04", machine_server: "ocp-r660-dl04", state: "deleting" }),
        node({ machine: null, state: "missing", node_name: null }),
      ])
    );
    expect(servers).toEqual([
      { name: "ocp-r660-dl01", label: "ocp-r660-DL01", node: "worker-0", state: "ready", why: null },
      { name: "worker-7", label: "worker-7", node: "worker-7", state: "not_ready", why: null },
      { name: null, label: "pool-c", node: null, state: "waiting", why: "Not installed yet: no server to name" },
      { name: "ocp-r660-dl04", label: "ocp-r660-DL04", node: "worker-0", state: "deleting", why: "Already leaving" },
    ]);
    expect(serversOf(undefined)).toEqual([]);
  });
});

describe("the picks", () => {
  it("are sent when none, or exactly as many as leave", () => {
    expect(picksReady(0, 2)).toBe(true);
    expect(picksReady(1, 2)).toBe(false);
    expect(picksReady(2, 2)).toBe(true);
  });

  it("say how many are picked and what that does", () => {
    expect(pickedWords(0, 1)).toBe("Optional: tick the server to remove, or none and the NodePool's scale-down policy picks.");
    expect(pickedWords(0, 2)).toBe("Optional: tick the 2 servers to remove, or none and the NodePool's scale-down policy picks.");
    expect(pickedWords(1, 3)).toBe("1 of 3 picked: tick 2 more, or none.");
    expect(pickedWords(1, 1)).toBe("1 of 1 picked: exactly this one leaves.");
    expect(pickedWords(2, 2)).toBe("2 of 2 picked: exactly these leave.");
  });

  it("replace the policy's line once complete", () => {
    expect(pickedLeaving(["ocp-a", "ocp-b"])).toBe(
      "Removes exactly the 2 servers you picked: ocp-a, ocp-b. The NodePool's scale-down policy is not used."
    );
  });
});
