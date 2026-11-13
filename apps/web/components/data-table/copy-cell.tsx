"use client";

import { Copy } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/**
 * A cell that copies its value on click (or Enter/Space: it is a button),
 * with a toast either way, as segments-manager's UI does. `label` names what
 * is copied ("VLAN ID").
 */
export function CopyCell({ value, label, className }: { value: string | null; label: string; className?: string }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} copied to clipboard`);
    } catch {
      toast.error("Copy failed. Please copy manually.");
    }
  };
  return (
    <button
      type="button"
      onClick={() => void copy()}
      aria-label={`Copy ${label} ${value}`}
      title={`Copy ${label}`}
      className={cn(
        "group inline-flex items-center gap-1 whitespace-nowrap rounded px-1 -mx-1 text-left outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50",
        className
      )}
    >
      <span>{value}</span>
      <Copy aria-hidden className="h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-60 group-focus-visible:opacity-60" />
    </button>
  );
}
