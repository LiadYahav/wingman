"use client";

import Link from "next/link";
import { Menu } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { SidebarNav } from "./sidebar-nav";
import { UserMenu } from "./user-menu";
import { AreaSwitch } from "./area-switch";
import { EasterEgg, triggerEasterEgg } from "./easter-egg";
import { Sheet, SheetContent } from "@/components/ui/sheet";

const CLICKS_TO_TRIGGER = 5;
const RESET_MS = 2000;

function SidebarLogo() {
  const clickCount = useRef(0);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleLogoClick = useCallback(() => {
    clickCount.current += 1;
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => { clickCount.current = 0; }, RESET_MS);
    if (clickCount.current >= CLICKS_TO_TRIGGER) {
      clickCount.current = 0;
      triggerEasterEgg();
    }
  }, []);

  return (
    <Link href="/" className="flex h-14 items-center gap-2.5 px-4" onClick={handleLogoClick}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/wingman-logo.svg" alt="Wingman" width={32} height={32} className="rounded-lg" />
      <span className="text-[17px] font-semibold tracking-tight text-foreground">
        Wing<span className="text-primary">man</span>
      </span>
    </Link>
  );
}

function SidebarContent() {
  return (
    <div className="flex h-full w-full flex-col border-r border-sidebar-border bg-sidebar">
      <SidebarLogo />
      <div className="flex-1 overflow-y-auto pt-2">
        <SidebarNav />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden md:flex md:w-[220px] md:shrink-0">
        <SidebarContent />
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
