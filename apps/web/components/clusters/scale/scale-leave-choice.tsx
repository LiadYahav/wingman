"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { overrides, POLICY_NOTES, type LeaveChoice } from "@/lib/scale-leave";
import { cn } from "@/lib/utils";
import { ServerPicker, usePickable } from "./scale-server-picker";
import type { ScaleTabValue } from "./scale-tab";

/** One way to choose the servers that leave: a radio, its label, and what it opens when chosen. */
function Option({
  tab,
  value,
  label,
  detail,
  disabled = false,
  children,
}: {
  tab: ScaleTabValue;
  value: LeaveChoice;
  label: string;
  detail?: React.ReactNode;
  disabled?: boolean;
  children?: React.ReactNode;
}) {
  const { choice, choose, start } = tab.state;
  const chosen = choice === value;
  return (
    <li className={cn("rounded-md px-2.5 py-1.5", chosen && "bg-primary/5")} data-testid={`scale-leave-${value}`}>
      <label className={cn("flex items-start gap-2.5 text-sm", disabled ? "cursor-not-allowed text-muted-foreground" : "cursor-pointer")}>
        <input
          type="radio"
          name="scale-leave"
          value={value}
          checked={chosen}
          onChange={() => choose(value)}
          disabled={disabled || start.isPending}
          className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
        />
        <span className="min-w-0">
          <span className="font-medium">{label}</span>
          {detail && <span className="block text-xs text-muted-foreground break-words">{detail}</span>}
        </span>
      </label>
      {chosen && children && <div className="mt-2 pl-6.5">{children}</div>}
    </li>
  );
}

/** "Another policy for this run": the workflow's policies but the NodePool's own, and what the chosen one removes. */
function PolicyPick({ tab }: { tab: ScaleTabValue }) {
  const { own, policy, choosePolicy, start } = tab.state;
  const items = overrides(own).map((p) => ({ value: p, label: p }));
  return (
    <div className="space-y-1">
      <Select value={policy} onValueChange={(p) => p && choosePolicy(p)} items={items} disabled={start.isPending}>
        <SelectTrigger size="sm" className="w-full font-mono sm:w-64" aria-label="Policy for this run" data-testid="scale-leave-policy-select">
          <SelectValue />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false}>
          {items.map((p) => (
            <SelectItem key={p.value} value={p.value} className="font-mono">
              {p.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground" data-testid="scale-leave-policy-note">
        Removes {POLICY_NOTES[policy]}. Only this run; the NodePool keeps its own.
      </p>
    </div>
  );
}

/**
 * In a scale-down's confirmation, which servers leave (ADR-0062's last
 * 2026-11-18 amendment): one choice, and exactly one answer sent. The
 * NodePool's own policy (the default: nothing is sent, the workflow reads it
 * off the NodePool), another policy for this run (`scale_down_policy`), or
 * the servers ticked (`server_names`). Picking needs the NodePool's nodes from
 * the MCE: without live status it is not offered, and says why.
 */
export function LeaveChoice({ tab }: { tab: ScaleTabValue }) {
  const { change, leaving, own } = tab.state;
  const offered = usePickable(tab);
  if (!change || leaving <= 0) return null;
  const noNodes = offered.length === 0;
  return (
    <fieldset className="space-y-1 rounded-lg border px-1.5 pb-1.5 pt-1" data-testid="scale-leave-choice">
      <legend className="px-1.5 text-xs font-semibold">Which servers leave</legend>
      <ul className="space-y-0.5">
        <Option
          tab={tab}
          value="own"
          label="The NodePool's own policy"
          detail={<span className={cn(own !== null && "font-mono")}>{own ?? "the platform default: CAPI picks at random"}</span>}
        />
        <Option tab={tab} value="policy" label="Another policy for this run">
          <PolicyPick tab={tab} />
        </Option>
        <Option
          tab={tab}
          value="servers"
          label="Pick the servers"
          disabled={noNodes}
          detail={
            noNodes ? (
              <span data-testid="scale-pick-none">Needs this NodePool&apos;s nodes from the MCE (live status).</span>
            ) : undefined
          }
        >
          <ServerPicker tab={tab} offered={offered} />
        </Option>
      </ul>
    </fieldset>
  );
}
