"use client";

import Link from "next/link";
import { Menu } from "lucide-react";
import { useState } from "react";
import { SidebarNav } from "./sidebar-nav";
import { UserMenu } from "./user-menu";
import { Sheet, SheetContent } from "@/components/ui/sheet";

function SidebarLogo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-4 py-5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/wingman-logo.svg" alt="Wingman" width={38} height={38} className="rounded-lg" />
      <span
        className="text-[19px] text-white"
        style={{ fontFamily: "var(--font-grotesk, var(--font-heading))", fontWeight: 500, letterSpacing: "-0.035em" }}
      >
        Wing<span style={{ color: "#5b78b8" }}>man</span>
      </span>
    </Link>
  );
}

function SidebarContent() {
  return (
    <div className="flex h-full flex-col bg-sidebar">
      <SidebarLogo />
      <div className="h-px mx-3 bg-sidebar-border" />
      <div className="flex-1 overflow-y-auto py-2">
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
        {/* Top header — clean white bar */}
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
          <button
            className="md:hidden inline-flex items-center justify-center rounded-lg hover:bg-muted size-8 text-muted-foreground transition-colors"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex-1" />
          <UserMenu />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-background">
          {children}
        </main>
      </div>
    </div>
  );
}
