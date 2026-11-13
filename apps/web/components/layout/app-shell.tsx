"use client";

import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { useState } from "react";
import { UserMenu } from "./user-menu";
import { AreaBrand } from "./area-brand";
import { AreaSidebar } from "./area-sidebar";
import { AreaSwitch } from "./area-switch";
import { EasterEgg } from "./easter-egg";
import { useAreaAccess } from "./use-area-access";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { chromeArea, type AreaId } from "@/lib/areas";

/** The current area's brand and sidebar: each platform wears its own (ADR-0047's amendment). */
function SidebarContent({ area }: { area: AreaId }) {
  return (
    <div className="flex h-full w-full flex-col border-r border-sidebar-border bg-sidebar" data-area={area}>
      <AreaBrand area={area} />
      <div className="flex-1 overflow-y-auto pt-2">
        <AreaSidebar area={area} />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const area = chromeArea(usePathname(), useAreaAccess());

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden md:flex md:w-[220px] md:shrink-0">
        <SidebarContent area={area} />
      </div>

      {/* Mobile sidebar */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="p-0 w-[220px] border-0">
          <SidebarContent area={area} />
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
          <AreaSwitch />
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
