"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ExternalLink, Plane, ScanSearch, Server, type LucideIcon } from "lucide-react";
import { chromeArea, switchEntries, type AreaId } from "@/lib/areas";
import { cn } from "@/lib/utils";
import { useAreaAccess } from "./use-area-access";
import { usePlatforms } from "./use-platforms";

const ICONS: Record<AreaId, LucideIcon> = { wingman: Plane, segments: Server, "server-scan": ScanSearch };

const ENTRY =
  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50";
const IDLE = "text-muted-foreground hover:text-foreground";

/**
 * The top bar's platform switch: plain links, one per area this person has,
 * the current one marked. A platform whose area is off here (the team keeps
 * segments-manager and server-scan apart, 2026-11-23) is a link to its own
 * UI, in a new tab, marked as leaving Wingman. With Wingman's entry alone (a
 * viewer, or neither system configured) there is nothing to switch to, so it
 * is not shown.
 */
export function AreaSwitch() {
  const access = useAreaAccess();
  // The area whose chrome the page wears: Wingman's on /server-scan while that area is off
  const current = chromeArea(usePathname(), access);
  const entries = switchEntries(access, usePlatforms());
  if (entries.length < 2) return null;
  return (
    <nav aria-label="Platform" className="inline-flex items-center gap-0.5 rounded-lg bg-muted p-0.5">
      {entries.map((entry) => {
        const Icon = ICONS[entry.id];
        if (entry.external) {
          return (
            <a key={entry.id} href={entry.href} target="_blank" rel="noopener noreferrer" className={cn(ENTRY, IDLE)}>
              <Icon aria-hidden className="h-3.5 w-3.5" />
              {entry.label}
              <ExternalLink aria-hidden className="h-3 w-3" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          );
        }
        const active = entry.id === current;
        return (
          <Link
            key={entry.id}
            href={entry.href}
            aria-current={active ? "page" : undefined}
            className={cn(ENTRY, active ? "bg-background text-foreground shadow-sm" : IDLE)}
          >
            <Icon aria-hidden className={cn("h-3.5 w-3.5", active && "text-primary")} />
            {entry.label}
          </Link>
        );
      })}
    </nav>
  );
}
