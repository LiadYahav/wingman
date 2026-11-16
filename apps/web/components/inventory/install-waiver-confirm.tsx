"use client";

import type { ReactNode } from "react";
import { ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { STILL_REFUSED, WAIVED } from "@/lib/inventory/waiver";
import type { Candidate } from "@/types/inventory";

function Line({ icon: Icon, tone, children }: { icon: typeof ShieldAlert; tone: string; children: ReactNode }) {
  return (
    <li className="flex gap-2 text-sm">
      <Icon aria-hidden className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
      <span>{children}</span>
    </li>
  );
}

/**
 * The step before a named install of servers that need a fix (ADR-0057's
 * 3.38.0 amendment): each such server with what server-scan shows wrong,
 * what the workflow then waives (for every server of the request) and what
 * it still refuses. Nothing is sent from here but by the dialog's confirm.
 */
export function InstallWaiverConfirm({ servers, total }: { servers: Candidate[]; total: number }) {
  const others = total - servers.length;
  return (
    <div className="grid gap-3" data-testid="waiver-confirm">
      <ul className="divide-y divide-border/60 rounded-lg border" aria-label="Servers that need a fix">
        {servers.map((server) => (
          <li key={server.id} className="grid gap-0.5 px-2.5 py-1.5 text-xs" data-testid="waiver-server" data-server={server.name}>
            <span className="break-all font-mono">{server.name}</span>
            <span className="text-status-warning-fg">{server.health_problems.join(" · ") || `health ${server.health}`}</span>
          </li>
        ))}
      </ul>
      <ul className="space-y-2" aria-label="What it means">
        <Line icon={ShieldAlert} tone="text-status-warning-fg">
          The workflow waives its health checks for{" "}
          {others > 0 ? `all ${total} servers of this request, the ${others} ready too` : total === 1 ? "this server" : `these ${total} servers`}:{" "}
          {WAIVED}.
        </Line>
        <Line icon={ShieldCheck} tone="text-muted-foreground">
          Its safety checks still apply: it refuses {STILL_REFUSED}.
        </Line>
        <Line icon={TriangleAlert} tone="text-muted-foreground">
          The server may join a NodePool with one NIC up or a storage fault. The run lists what it waived.
        </Line>
      </ul>
    </div>
  );
}
