import { cn } from "@/lib/utils";

type Phase = "Provisioning" | "Ready" | "Error" | "Deleting" | "Unknown";

const phaseConfig: Record<
  Phase,
  { label: string; dotClass: string; bgClass: string; textClass: string }
> = {
  Ready: {
    label: "Ready",
    dotClass: "bg-[#00c875]",
    bgClass: "bg-[#00c875]/10 dark:bg-[#00c875]/15",
    textClass: "text-[#007038] dark:text-[#00c875]",
  },
  Provisioning: {
    label: "Provisioning",
    dotClass: "bg-[#579bfc] animate-pulse",
    bgClass: "bg-[#579bfc]/10 dark:bg-[#579bfc]/15",
    textClass: "text-[#0060b9] dark:text-[#579bfc]",
  },
  Error: {
    label: "Error",
    dotClass: "bg-[#df2f4a]",
    bgClass: "bg-[#df2f4a]/10 dark:bg-[#df2f4a]/15",
    textClass: "text-[#a0122a] dark:text-[#df2f4a]",
  },
  Deleting: {
    label: "Deleting",
    dotClass: "bg-[#fdab3d] animate-pulse",
    bgClass: "bg-[#fdab3d]/10 dark:bg-[#fdab3d]/15",
    textClass: "text-[#c07800] dark:text-[#fdab3d]",
  },
  Unknown: {
    label: "Unknown",
    dotClass: "bg-muted-foreground/40",
    bgClass: "bg-muted",
    textClass: "text-muted-foreground",
  },
};

export function StatusBadge({ phase }: { phase: Phase }) {
  const config = phaseConfig[phase] ?? phaseConfig.Unknown;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        config.bgClass,
        config.textClass
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", config.dotClass)} />
      {config.label}
    </span>
  );
}
