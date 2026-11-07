import { cn } from "@/lib/utils";

type Phase = "Provisioning" | "Ready" | "Error" | "Deleting" | "Unknown";

const phaseConfig: Record<
  Phase,
  { label: string; dotClass: string; chipClass: string }
> = {
  Ready: {
    label: "Ready",
    dotClass: "bg-status-ready",
    chipClass: "bg-status-ready/15 text-status-ready-fg ring-status-ready/25",
  },
  Provisioning: {
    label: "Provisioning",
    dotClass: "bg-status-provisioning animate-pulse",
    chipClass: "bg-status-provisioning/15 text-status-provisioning-fg ring-status-provisioning/25",
  },
  Error: {
    label: "Error",
    dotClass: "bg-status-error",
    chipClass: "bg-status-error/15 text-status-error-fg ring-status-error/25",
  },
  Deleting: {
    label: "Deleting",
    dotClass: "bg-status-warning animate-pulse",
    chipClass: "bg-status-warning/15 text-status-warning-fg ring-status-warning/25",
  },
  Unknown: {
    label: "Unknown",
    dotClass: "bg-status-deleting",
    chipClass: "bg-status-deleting/15 text-status-deleting-fg ring-status-deleting/25",
  },
};

export function StatusBadge({ phase }: { phase: Phase }) {
  const config = phaseConfig[phase] ?? phaseConfig.Unknown;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        config.chipClass
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", config.dotClass)} />
      {config.label}
    </span>
  );
}
