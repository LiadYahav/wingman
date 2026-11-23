"use client";

import { Menu } from "lucide-react";
import { useState } from "react";
import { UserMenu } from "./user-menu";
import { Brand } from "./brand";
import { PlatformSwitch } from "./platform-switch";
import { EasterEgg } from "./easter-egg";
import { SidebarNav } from "./sidebar-nav";
import { SidebarToggle } from "./sidebar-toggle";
import { SidebarRailContext, useSidebarRailState } from "./use-sidebar-rail";
import { Sheet, SheetContent } from "@/components/ui/sheet";

/** The desktop sidebar's element: the toggle names it as what it controls. */
const DESKTOP_SIDEBAR_ID = "app-sidebar";

/**
 * Wingman's brand and sidebar. The desktop copy has the toggle to the icon
 * rail; the mobile sheet's has none and is never a rail.
 */
function SidebarContent({ desktop = false }: { desktop?: boolean }) {
  return (
    <div className="flex h-full w-full flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex shrink-0 items-center pr-3 rail:flex-col rail:pb-1 rail:pr-0">
        <Brand />
        {desktop && <SidebarToggle controls={DESKTOP_SIDEBAR_ID} />}
      </div>
      <div className="flex-1 overflow-x-hidden overflow-y-auto pt-2">
        <SidebarNav />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const rail = useSidebarRailState();

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop sidebar: --app-sidebar-width is the rail's or the full width (globals.css), set before the first paint */}
      <div
        id={DESKTOP_SIDEBAR_ID}
        data-desktop-sidebar
        className="hidden overflow-hidden md:flex md:w-(--app-sidebar-width) md:shrink-0 motion-safe:transition-[width] motion-safe:duration-200 motion-safe:ease-out"
      >
        <SidebarRailContext value={rail}>
          <SidebarContent desktop />
        </SidebarRailContext>
      </div>

      {/* Mobile sidebar */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="p-0 w-[220px] border-0">
          <SidebarContent />
        </SheetContent>
      </Sheet>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top header — translucent, blurs content scrolling beneath it */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background/70 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-background/60">
          <button
            aria-label="Open navigation"
            className="md:hidden inline-flex items-center justify-center rounded-lg hover:bg-muted size-8 text-muted-foreground transition-colors"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <PlatformSwitch />
          <div className="flex-1" />
          <UserMenu />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
      <EasterEgg />
    </div>
  );
}
