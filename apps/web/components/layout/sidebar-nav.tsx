"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Server, Package, GitPullRequest, ClipboardList, Settings, Layers, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard, exact: true },
  { label: "Clusters", href: "/clusters", icon: Server },
  { label: "Specs", href: "/specs", icon: Layers },
  { label: "Addons", href: "/addons", icon: Package },
  { label: "Approvals", href: "/approvals", icon: GitPullRequest },
  { label: "Audit", href: "/audit", icon: ClipboardList },
  { label: "Documentation", href: "/docs", icon: BookOpen },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function SidebarNav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-0.5 px-2 py-2">
      {navItems.map((item) => {
        const isActive = item.exact
          ? pathname === item.href
          : pathname === item.href || pathname.startsWith(item.href + "/");
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150",
              isActive
                ? "bg-white/15 text-white"
                : "text-sidebar-foreground/70 hover:bg-white/8 hover:text-sidebar-foreground"
            )}
          >
            <item.icon
              className={cn(
                "h-4 w-4 shrink-0 transition-colors",
                isActive ? "text-white" : "text-sidebar-foreground/50"
              )}
            />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
