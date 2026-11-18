/**
 * The one scale change the Nodes tab holds (ADR-0062, its amendments): one
 * NodePool's replicas, on its card or its NodePool sizes row, sent as one
 * update-nodepool run, with, on a scale-down, one choice of which servers
 * leave (`scale-leave.ts`): the NodePool's own policy (the default, sends
 * nothing), another policy for this run, or exactly as many servers picked
 * as leave. Changing a stepper makes it the change, puts every other stepper
 * back at its value now and drops the choice; setting it back to its value
 * now leaves nothing to send. Sent once, never retried (ADR-0006).
 */

import { useRef, useState } from "react";
import { useStartScale } from "@/lib/scale";
import { leaveFields, leaveReady, overrideOf, ownPolicy, type LeaveChoice } from "@/lib/scale-leave";
import { currentOf, directionOf, replicasOf, startBody, type ScaleChange } from "@/lib/scale-model";
import type { ScaleOptions, ScaleRun } from "@/types";

/** `options`: `null` while scaling is off or not read yet; nothing can change then. */
export function useScaleChange(name: string, where: string, options: ScaleOptions | null) {
  const [change, setChange] = useState<ScaleChange | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [choice, setChoice] = useState<LeaveChoice>("own");
  const [picked, setPicked] = useState<string | null>(null);
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
  /** How many servers a scale-down removes; 0 for anything else, so a scale-up never says which leave. */
  const leaving = direction === "down" && current !== null && asked !== null ? current - asked : 0;
  /** The NodePool's own policy in the day1 file: `null` none, `undefined` while there is no change. */
  const own = change && options ? ownPolicy(change.nodepool, options.nodepools) : undefined;
  const policy = overrideOf(picked, own);
  const ticked = leaving > 0 && choice === "servers" ? servers : [];

  const reset = () => {
    setConfirming(false);
    setChoice("own");
    setPicked(null);
    setServers([]);
  };
  const edit = (nodepool: string, replicas: number) => {
    start.reset();
    reset();
    setChange(replicas === nowOf(nodepool) ? null : { nodepool, replicas });
  };
  const cancel = () => {
    start.reset();
    reset();
    setChange(null);
  };
  /** Opens or closes the confirmation; closed, its choice is dropped (the change stays). */
  const confirm = (open: boolean) => {
    if (!open) reset();
    setConfirming(open);
  };
  /** Which way the servers that leave are chosen; leaving "pick the servers" drops the ticks. */
  const choose = (next: LeaveChoice) => {
    start.reset();
    setChoice(next);
    if (next !== "servers") setServers([]);
  };
  /** The policy for this run, among the ones the choice offers. */
  const choosePolicy = (next: string) => {
    start.reset();
    setPicked(next);
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
  const ready = leaveReady(choice, ticked.length, leaving);
  const send = (onStarted: (run: ScaleRun) => void) => {
    const body = pending && ready ? startBody(pending.nodepool, pending.replicas, leaveFields(choice, leaving, ticked, policy)) : null;
    if (!body || sending.current || start.isPending) return;
    sending.current = true;
    start.mutate(body, {
      onSuccess: (run) => {
        reset();
        setChange(null);
        onStarted(run);
      },
      onSettled: () => {
        sending.current = false;
      },
    });
  };

  return {
    change: pending, current, asked, direction, leaving, own: own ?? null, choice, policy, servers: ticked, ready,
    confirming, setConfirming: confirm, start, edit, cancel, choose, choosePolicy, toggleServer, valueOf, send,
  };
}

export type ScaleChangeState = ReturnType<typeof useScaleChange>;
