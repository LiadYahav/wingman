import { FileWarning, TriangleAlert } from "lucide-react";
import type { ClusterDetail } from "@/types";

/** A file that does not parse: the problems, in full. */
export function FileProblems({ problems }: { problems: string[] }) {
  if (problems.length === 0) return null;
  return (
    <div role="alert" className="rounded-xl border border-status-error/30 bg-status-error/5 p-4 text-sm">
      <p className="flex items-center gap-2 font-semibold text-status-error-fg">
        <FileWarning className="h-4 w-4 shrink-0" />The cluster file does not parse
      </p>
      <ul className="mt-2 list-disc pl-6 space-y-0.5 text-status-error-fg/90">
        {problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">Its values cannot be shown; the YAML tab has the raw file.</p>
    </div>
  );
}

/** A name off `ocp4-<env>-<name>-<site>[-<seq>]` is flagged, never hidden. */
export function NamingNotice({ cluster }: { cluster: ClusterDetail }) {
  if (cluster.naming.follows_convention) return null;
  return (
    <div className="rounded-xl border border-status-warning/30 bg-status-warning/5 p-4 text-sm">
      <p className="flex items-center gap-2 font-semibold text-status-warning-fg">
        <TriangleAlert className="h-4 w-4 shrink-0" />Off the naming convention
      </p>
      <ul className="mt-2 list-disc pl-6 space-y-0.5 text-muted-foreground">
        {cluster.naming.problems.map((p, i) => <li key={i} className="break-words">{p}</li>)}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        Existing clusters keep working; Wingman only refuses such names for new clusters.
      </p>
    </div>
  );
}
