import { cn } from "@/lib/utils";
import type { MRDetail } from "@/types";

const REPO_CLASSES: Record<MRDetail["repo"], string> = {
  day1: "bg-primary/10 text-primary dark:bg-status-provisioning/15 dark:text-status-provisioning",
  day2: "bg-status-ready/10 text-status-ready-fg dark:bg-status-ready/15 dark:text-status-ready",
  specs: "bg-chart-5/10 text-chart-5 dark:bg-chart-5/15 dark:text-[#c490f0]",
};

/** Which repository an MR or commit is in; day2 items also name their team. */
export function RepoBadge({ repo, team, className }: { repo: MRDetail["repo"]; team?: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        REPO_CLASSES[repo] ?? "bg-muted text-muted-foreground",
        className
      )}
    >
      {repo === "day2" && team ? `day2 · ${team}` : repo}
    </span>
  );
}
