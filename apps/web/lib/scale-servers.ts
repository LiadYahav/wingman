/**
 * Picking the servers a scale-down removes (ADR-0062's 2026-11-18
 * amendment), as pure functions: one of the ways the servers that leave are
 * chosen (`scale-leave.ts`), and then exactly as many as leave. The
 * names are each node's `machine_server`, the workflow's own rule for which
 * server a Machine is, so what is sent is what it matches. Which Machine a
 * name is, and whether CAPI would take another, stay the workflow's to judge.
 */

import { plural } from "@/lib/utils";
import type { NodePoolNodes, NodeState } from "@/types";

/** One node of the NodePool, as the picker offers it. */
export interface PickableServer {
  /** What is sent: the workflow's name for the Machine's server; `null` when it has none. */
  name: string | null;
  /** What is shown: server-scan's name when it knows the server, else the workflow's, else the Machine. */
  label: string;
  node: string | null;
  state: NodeState;
  /** Why it cannot be picked; `null` when it can. */
  why: string | null;
}

/** The NodePool's Machines (not its missing rows), each with the name a scale-down would send for it. */
export function serversOf(pool: NodePoolNodes | undefined): PickableServer[] {
  return (pool?.nodes ?? [])
    .filter((n) => n.machine !== null)
    .map((n) => ({
      name: n.machine_server,
      label: n.server_name ?? n.machine_server ?? (n.machine as string),
      node: n.node_name,
      state: n.state,
      why: n.machine_server === null ? "Not installed yet: no server to name" : n.state === "deleting" ? "Already leaving" : null,
    }));
}

/** Under the list: how many are picked, and what that means (exactly as many as leave are sent). */
export function pickedWords(picked: number, leaving: number): string {
  if (picked === 0) return `Tick ${leaving === 1 ? "the server" : `the ${leaving} servers`} to remove.`;
  if (picked < leaving) return `${picked} of ${leaving} picked: tick ${leaving - picked} more.`;
  return `${picked} of ${leaving} picked: exactly ${picked === 1 ? "this one leaves" : "these leave"}.`;
}

/** The scale-down's main line once every server that leaves is picked. */
export function pickedLeaving(servers: string[]): string {
  return `Removes exactly the ${plural(servers.length, "server")} you picked: ${servers.join(", ")}. The NodePool's scale-down policy is not used.`;
}
