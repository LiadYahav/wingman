/**
 * The one scale change the Nodes tab holds (ADR-0062, its amendments): one
 * NodePool's replicas, on its card or its NodePool sizes row, sent as one
 * update-nodepool run, with, on a scale-down, the servers picked to leave
 * (none, or exactly as many as leave). Changing a stepper makes it the
 * change, puts every other stepper back at its value now and drops the
 * picks; setting it back to its value now leaves nothing to send. Sent
 * once, never retried (ADR-0006).
 */

import { useRef, useState } from "react";
import { useStartScale } from "@/lib/scale";
import { currentOf, directionOf, replicasOf, startBody, type ScaleChange } from "@/lib/scale-model";
import { picksReady } from "@/lib/scale-servers";
import type { ScaleOptions, ScaleRun } from "@/types";

/** `options`: `null` while scaling is off or not read yet; nothing can change then. */
export function useScaleChange(name: string, where: string, options: ScaleOptions | null) {
  const [change, setChange] = useState<ScaleChange | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [servers, setServers] = useState<string[]>([]);
  const start = useStartScale(name, where);
  // A second click lands before the pending state renders: the ref holds the start back
  const sending = useRef(false);
  const nowOf = (nodepool: string) => (options ? currentOf(nodepool, options.nodepools) : null);

  const current = change ? nowOf(change.nodepool) : null;
  const asked = change ? replicasOf(change.replicas) : null;
  const direction = directionOf(current, asked);
  // Back at its value now (typed, or after the sizes were read again): nothing to send
  const pending = change && direction !== "none" ? change : null;
  /** How many servers a scale-down removes; 0 for anything else, so a scale-up never sends a name. */
  const leaving = direction === "down" && current !== null && asked !== null ? current - asked : 0;
  const picked = leaving > 0 ? servers : [];

  const edit = (nodepool: string, replicas: number) => {
    start.reset();
    setConfirming(false);
    setServers([]);
    setChange(replicas === nowOf(nodepool) ? null : { nodepool, replicas });
  };
  const cancel = () => {
    start.reset();
    setConfirming(false);
    setServers([]);
    setChange(null);
  };
  /** Opens or closes the confirmation; closed, its picks are dropped (the change stays). */
  const confirm = (open: boolean) => {
    setConfirming(open);
    if (!open) setServers([]);
  };
  /** Ticks or unticks a server; never more than leave. */
  const toggleServer = (server: string) => {
    start.reset();
    setServers((now) => (now.includes(server) ? now.filter((s) => s !== server) : now.length < leaving ? [...now, server] : now));
  };
  /** What a stepper shows: the change's number when it is the change, else its value now. */
  const valueOf = (nodepool: string): number => {
    if (pending && pending.nodepool === nodepool) return pending.replicas;
    return nowOf(nodepool) ?? NaN;
  };
  const send = (onStarted: (run: ScaleRun) => void) => {
    const body = pending && picksReady(picked.length, leaving) ? startBody(pending.nodepool, pending.replicas, picked) : null;
    if (!body || sending.current || start.isPending) return;
    sending.current = true;
    start.mutate(body, {
      onSuccess: (run) => {
        setConfirming(false);
        setServers([]);
        setChange(null);
        onStarted(run);
      },
      onSettled: () => {
        sending.current = false;
      },
    });
  };

  return {
    change: pending, current, asked, direction, leaving, servers: picked, confirming, setConfirming: confirm, start,
    edit, cancel, toggleServer, valueOf, send,
  };
}

export type ScaleChangeState = ReturnType<typeof useScaleChange>;
