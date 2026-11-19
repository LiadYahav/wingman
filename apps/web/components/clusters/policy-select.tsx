"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { POLICIES, policyNote, policyOf } from "@/lib/nodepool-policy";

/** The select's value for none: Base UI keys an item by its value, and none is no value. */
const DEFAULT = "platform-default";

/**
 * A nodepool's scale-down policy (ADR-0062): the platform default (nothing
 * written, CAPI picks at random) or one of update-nodepool's three, each
 * explained in a line, and the chosen one's line under it. A value the file
 * holds that the workflow does not know is shown as written. Read only, it
 * is its value and that line.
 */
export function PolicySelect({
  value,
  onChange,
  readOnly = false,
  label,
  testId,
}: {
  value: unknown;
  /** `null`: the platform default. */
  onChange: (policy: string | null) => void;
  readOnly?: boolean;
  label: string;
  testId: string;
}) {
  const policy = policyOf(value);
  const unknown = policy !== null && !POLICIES.some((p) => p.value === policy);
  const items = [
    { value: DEFAULT, label: "Platform default", note: "CAPI picks at random." },
    ...POLICIES.map((p) => ({ value: p.value as string, label: p.value as string, note: p.note as string })),
    ...(unknown ? [{ value: policy, label: policy, note: "Not a policy update-nodepool knows." }] : []),
  ];
  return (
    <div className="min-w-0 space-y-1" data-testid={testId}>
      {readOnly ? (
        <p className="text-sm" data-testid={`${testId}-value`}>
          {policy === null ? "Platform default" : <span className="font-mono">{policy}</span>}
        </p>
      ) : (
        <Select value={policy ?? DEFAULT} onValueChange={(next) => next && onChange(next === DEFAULT ? null : next)} items={items}>
          <SelectTrigger className="w-56 max-w-full" aria-label={label} data-testid={`${testId}-trigger`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false} className="w-80 max-w-[calc(100vw-2rem)]">
            {items.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                <span className="flex min-w-0 flex-col py-0.5">
                  <span className={item.value === DEFAULT ? undefined : "font-mono"}>{item.label}</span>
                  <span className="text-xs whitespace-normal text-muted-foreground">{item.note}</span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      <p className="text-xs text-muted-foreground" data-testid={`${testId}-note`}>
        {policyNote(policy)}
      </p>
    </div>
  );
}
