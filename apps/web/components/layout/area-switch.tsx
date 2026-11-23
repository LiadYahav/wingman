"use client";

import Link from "next/link";
import { ExternalLink, Plane, ScanSearch, Server, type LucideIcon } from "lucide-react";
import { switchEntries, type SwitchEntry } from "@/lib/areas";
import { cn } from "@/lib/utils";
import { usePlatforms } from "./use-platforms";

const ICONS: Record<SwitchEntry["id"], LucideIcon> = { wingman: Plane, segments: Server, "server-scan": ScanSearch };

const ENTRY =
  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50";

/**
 * The top bar's platform switch: Wingman, marked as where you are, then a
 * link to each system the team keeps apart from Wingman (segments-manager,
 * server-scan; 2026-11-23), its own UI in a new tab, marked as leaving
 * Wingman. With Wingman's entry alone (a viewer, or neither system
 * configured) there is nothing to switch to, so it is not shown.
 */
export function AreaSwitch() {
  const entries = switchEntries(usePlatforms());
  if (entries.length < 2) return null;
  return (
    <nav aria-label="Platform" className="inline-flex items-center gap-0.5 rounded-lg bg-muted p-0.5">
      {entries.map((entry) => {
        const Icon = ICONS[entry.id];
        if (entry.external) {
          return (
            <a
              key={entry.id}
              href={entry.href}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(ENTRY, "text-muted-foreground hover:text-foreground")}
            >
              <Icon aria-hidden className="h-3.5 w-3.5" />
              {entry.label}
              <ExternalLink aria-hidden className="h-3 w-3" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          );
        }
        return (
          <Link key={entry.id} href={entry.href} aria-current="page" className={cn(ENTRY, "bg-background text-foreground shadow-sm")}>
            <Icon aria-hidden className="h-3.5 w-3.5 text-primary" />
            {entry.label}
          </Link>
        );
      })}
    </nav>
  );
}
