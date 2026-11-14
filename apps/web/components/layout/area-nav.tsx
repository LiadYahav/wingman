"use client";

import { BookOpen, CalendarClock, CircleDashed, CircleDot, Cpu, Layers, ListChecks, MapPin, Network, ScrollText, Server, Sparkles, TriangleAlert, type LucideIcon } from "lucide-react";
import type { NavIcon, NavSection } from "@/lib/areas";
import { SidebarHeading, SidebarLink, SidebarNavList } from "./sidebar-parts";

const ICONS: Record<NavIcon, LucideIcon> = {
  all: Layers,
  available: CircleDashed,
  allocated: CircleDot,
  mismatch: TriangleAlert,
  site: MapPin,
  servers: Server,
  confs: Cpu,
  rules: ListChecks,
  events: ScrollText,
  jobs: CalendarClock,
  docs: BookOpen,
  claude: Sparkles,
  architecture: Network,
};

/**
 * An area's sidebar from data (`lib/areas.ts`'s `NavSection`), in the look of
 * Wingman's own and from the same parts (sidebar-parts.tsx), so it collapses
 * to the icon rail the same way: grouped links, the active one marked with a
 * bar and `aria-current`. `label` names the navigation landmark.
 */
export function AreaNav({ label, sections }: { label: string; sections: NavSection[] }) {
  return (
    <SidebarNavList label={label}>
      {sections.map((section, index) => (
        <div key={section.label} className="flex flex-col gap-0.5" data-testid="area-nav-section">
          <SidebarHeading label={section.label} first={index === 0} />
          {section.note && <p className="px-2.5 py-1 text-xs text-sidebar-foreground/60 rail:sr-only">{section.note}</p>}
          {section.items.map((item) => (
            <SidebarLink
              key={item.key}
              testId={`area-nav-${item.key}`}
              href={item.href}
              label={item.label}
              icon={ICONS[item.icon]}
              active={item.active}
              meta={item.meta}
              metaLabel={item.metaLabel}
            />
          ))}
        </div>
      ))}
    </SidebarNavList>
  );
}
