"use client";

import { useSyncExternalStore } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { sidebarShortcutLabel } from "@/lib/sidebar-rail";
import { useSidebarRail } from "./use-sidebar-rail";

const noSubscription = () => () => {};

/** The shortcut as this platform writes it; only in the browser, where the tooltip renders. */
function ShortcutHint() {
  const shortcut = useSyncExternalStore(noSubscription, () => sidebarShortcutLabel(navigator.platform), () => "Ctrl+B");
  return (
    <kbd className="rounded-sm bg-background/20 px-1 font-sans text-[11px]" data-slot="kbd">
      {shortcut}
    </kbd>
  );
}

/**
 * Collapses the desktop sidebar to its icon rail and expands it again. The
 * same button in both (the CSS moves it below the mark in the rail), so focus
 * stays on it. Its icon follows the CSS too, so it is right before hydration.
 */
export function SidebarToggle({ controls }: { controls: string }) {
  const { collapsed, toggle } = useSidebarRail();
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  return (
    <Tooltip>
      <TooltipTrigger
        data-testid="sidebar-toggle"
        aria-label={label}
        aria-expanded={!collapsed}
        aria-controls={controls}
        onClick={toggle}
        className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-sidebar-foreground/60 outline-none transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <PanelLeftClose aria-hidden className="h-4 w-4 rail:hidden" />
        <PanelLeftOpen aria-hidden className="hidden h-4 w-4 rail:block" />
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {label}
        <ShortcutHint />
      </TooltipContent>
    </Tooltip>
  );
}
