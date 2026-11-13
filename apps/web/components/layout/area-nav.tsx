"use client";

import Link from "next/link";
import { BookOpen, CircleDashed, CircleDot, Layers, MapPin, Server, TriangleAlert, type LucideIcon } from "lucide-react";
import type { NavIcon, NavSection } from "@/lib/areas";
import { cn } from "@/lib/utils";

const ICONS: Record<NavIcon, LucideIcon> = {
  all: Layers,
  available: CircleDashed,
  allocated: CircleDot,
  mismatch: TriangleAlert,
  site: MapPin,
  servers: Server,
  docs: BookOpen,
};

/**
 * An area's sidebar from data (`lib/areas.ts`'s `NavSection`), in the look of
 * Wingman's own: grouped links, the active one marked with a bar and
 * `aria-current`. `label` names the navigation landmark.
 */
export function AreaNav({ label, sections }: { label: string; sections: NavSection[] }) {
  return (
    <nav className="flex flex-col gap-5 px-3 py-3" aria-label={label}>
      {sections.map((section) => (
        <div key={section.label} className="flex flex-col gap-0.5" data-testid="area-nav-section">
          <p className="px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/50">
            {section.label}
          </p>
          {section.note && <p className="px-2.5 py-1 text-xs text-sidebar-foreground/60">{section.note}</p>}
          {section.items.map((item) => {
            const Icon = ICONS[item.icon];
            return (
              <Link
                key={item.key}
                href={item.href}
                data-testid={`area-nav-${item.key}`}
                aria-current={item.active ? "page" : undefined}
                className={cn(
                  "group relative flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-150",
                  item.active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
                )}
              >
                {item.active && <span aria-hidden className="absolute inset-y-1.5 -left-3 w-0.5 rounded-full bg-sidebar-primary" />}
                <Icon
                  className={cn(
                    "h-4 w-4 shrink-0 transition-colors",
                    item.active ? "text-sidebar-primary" : "text-sidebar-foreground/60 group-hover:text-sidebar-foreground"
                  )}
                />
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {item.meta && (
                  <span className="shrink-0 text-[11px] tabular-nums text-sidebar-foreground/60" title={item.metaLabel}>
                    {item.meta}
                    {item.metaLabel && <span className="sr-only">: {item.metaLabel}</span>}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
