import { RotateCcw } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";

/**
 * A write refused with 409 REVISION_CONFLICT: what moved since the page read
 * it, and a Reload. Never retried (ADR-0006): the person reviews again.
 */
export function StaleAlert({ message, onReload }: { message: string; onReload: () => void }) {
  return (
    <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-status-warning/30 bg-status-warning/5 p-4 text-sm">
      <p className="text-status-warning-fg">{message}</p>
      <button onClick={onReload} className={buttonVariants({ variant: "outline", size: "sm" })}>
        <RotateCcw className="h-3.5 w-3.5 mr-1.5" />Reload
      </button>
    </div>
  );
}
