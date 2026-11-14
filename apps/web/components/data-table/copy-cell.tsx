"use client";

import { Copy } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/** Copy `value` to the clipboard, with a toast either way; `label` names what is copied ("VLAN ID"). */
async function copyValue(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value);
    toast.success(`${label} copied to clipboard`);
  } catch {
    toast.error("Copy failed. Please copy manually.");
  }
}

/**
 * A cell that copies its value on click (or Enter/Space: it is a button),
 * with a toast either way, as segments-manager's UI does. `label` names what
 * is copied ("VLAN ID").
 */
export function CopyCell({ value, label, className }: { value: string | null; label: string; className?: string }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const copy = () => copyValue(value, label);
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

/**
 * A copy button with only its icon, beside what it copies (a link, a title):
 * `label` names what is copied, and its name is "Copy <label> <value>", as a
 * `CopyCell`'s. `reveal` shows it only while its `group` is hovered or focused.
 */
export function CopyButton({ value, label, reveal = false, className }: { value: string; label: string; reveal?: boolean; className?: string }) {
  return (
    <button
      type="button"
      onClick={() => void copyValue(value, label)}
      aria-label={`Copy ${label} ${value}`}
      title={`Copy ${label}`}
      className={cn(
        "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
        reveal && "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100",
        className
      )}
    >
      <Copy aria-hidden className="h-3.5 w-3.5" />
    </button>
  );
}
