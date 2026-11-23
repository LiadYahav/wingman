"use client";

import Link from "next/link";
import { ExternalLink, type LucideIcon } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useSidebarRail } from "./use-sidebar-rail";

/*
 * The pieces Wingman's sidebar is built of (sidebar-nav.tsx), so it collapses
 * to the icon rail in one way. The rail's look is CSS (`rail:`, globals.css),
 * so it is right before React hydrates; React adds only the tooltips.
 */

/** The navigation landmark, `label` its name: groups of entries, closer together in the rail. */
export function SidebarNavList({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <nav className="flex flex-col gap-5 px-3 py-3 rail:gap-2 rail:px-2" aria-label={label}>
      {children}
    </nav>
  );
}

/** A group's heading; in the rail a thin divider (none above the first group: the brand is there). */
export function SidebarHeading({ label, first }: { label: string; first: boolean }) {
  return (
    <>
      {!first && <span aria-hidden className="mx-1.5 mb-1.5 hidden h-px bg-sidebar-border rail:block" />}
      <p className="px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/50 rail:sr-only">
        {label}
      </p>
    </>
  );
}

export interface SidebarLinkProps {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Marked as where you are. */
  active: boolean;
}

/**
 * An entry: its icon and label, the active one marked with a bar and
 * `aria-current`. In the rail only the icon shows; the label stays the
 * link's accessible name and shows in a tooltip on hover and focus.
 */
export function SidebarLink({ href, label, icon: Icon, active }: SidebarLinkProps) {
  const { collapsed } = useSidebarRail();
  return (
    <Tooltip disabled={!collapsed}>
      <TooltipTrigger
        render={<Link href={href} />}
        aria-current={active ? "page" : undefined}
        className={cn(
          "group relative flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-150 rail:h-8 rail:justify-center rail:px-0",
          active
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
        )}
      >
        {/* A bar, not just a colour change, so "where am I" doesn't rely on telling two greys apart. */}
        {active && <span aria-hidden className="absolute inset-y-1.5 -left-3 w-0.5 rounded-full bg-sidebar-primary rail:-left-2" />}
        <Icon
          aria-hidden
          className={cn(
            "h-4 w-4 shrink-0 transition-colors",
            active ? "text-sidebar-primary" : "text-sidebar-foreground/60 group-hover:text-sidebar-foreground"
          )}
        />
        <span className="min-w-0 flex-1 truncate rail:sr-only">{label}</span>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={10} data-testid="sidebar-tooltip">
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * An entry that leaves Wingman: another system's own UI in a new tab,
 * marked as leaving with a trailing arrow and in its accessible name. Never
 * marked as where you are.
 */
export function SidebarExternalLink({ href, label, icon: Icon }: Omit<SidebarLinkProps, "active">) {
  const { collapsed } = useSidebarRail();
  return (
    <Tooltip disabled={!collapsed}>
      <TooltipTrigger
        render={<a href={href} target="_blank" rel="noopener noreferrer" />}
        className="group relative flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium text-sidebar-foreground transition-colors duration-150 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground rail:h-8 rail:justify-center rail:px-0"
      >
        <Icon aria-hidden className="h-4 w-4 shrink-0 text-sidebar-foreground/60 transition-colors group-hover:text-sidebar-foreground" />
        <span className="min-w-0 flex-1 truncate rail:sr-only">{label}</span>
        <ExternalLink aria-hidden className="h-3 w-3 shrink-0 text-sidebar-foreground/40 rail:hidden" />
        <span className="sr-only">(opens in a new tab)</span>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={10} data-testid="sidebar-tooltip">
        {label} (opens in a new tab)
      </TooltipContent>
    </Tooltip>
  );
}
