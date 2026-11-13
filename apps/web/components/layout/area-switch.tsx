"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Network, Plane, type LucideIcon } from "lucide-react";
import { useSegmentsArea } from "@/lib/api/segments";
import { areaOf, areasFor, type AreaId } from "@/lib/areas";
import { cn } from "@/lib/utils";

const ICONS: Record<AreaId, LucideIcon> = { wingman: Plane, segments: Network };

/**
 * The top bar's area switch: plain links, one per area this person has, the
 * current one marked. With Wingman's area alone (a viewer, or segments-manager
 * not configured) there is nothing to switch to, so it is not shown.
 */
export function AreaSwitch() {
  const current = areaOf(usePathname());
  const areas = areasFor({ segments: useSegmentsArea() === true });
  if (areas.length < 2) return null;
  return (
    <nav aria-label="Areas" className="inline-flex items-center gap-0.5 rounded-lg bg-muted p-0.5">
      {areas.map((area) => {
        const active = area.id === current;
        const Icon = ICONS[area.id];
        return (
          <Link
            key={area.id}
            href={area.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50",
              active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon aria-hidden className={cn("h-3.5 w-3.5", active && "text-primary")} />
            {area.label}
          </Link>
        );
      })}
    </nav>
  );
}
