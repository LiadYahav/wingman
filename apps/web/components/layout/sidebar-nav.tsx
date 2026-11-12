"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { LayoutDashboard, Server, Package, GitPullRequest, ClipboardList, Settings, Layers, BookOpen, ShieldAlert, Link2, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useIsAdmin } from "@/stores/auth-store";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
  /** Shown to Wingman's admins only: the page's API refuses everyone else (for now, until finer roles). */
  adminOnly?: boolean;
}

const navGroups: { label: string; items: NavItem[] }[] = [
  {
    label: "Platform",
    items: [
      { label: "Dashboard", href: "/", icon: LayoutDashboard, exact: true },
      { label: "Clusters", href: "/clusters", icon: Server },
      { label: "Flavors", href: "/specs", icon: Layers },
      { label: "Addons", href: "/addons", icon: Package },
      { label: "Quick Links", href: "/quick-links", icon: Link2, adminOnly: true },
    ],
  },
  {
    label: "Governance",
    items: [
      { label: "Approvals", href: "/approvals", icon: GitPullRequest },
      { label: "Audit", href: "/audit", icon: ClipboardList },
      { label: "Lints", href: "/lints", icon: ShieldAlert },
    ],
  },
  {
    label: "Help",
    items: [
      { label: "Documentation", href: "/docs", icon: BookOpen },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

const noSubscription = () => () => {};

/**
 * False during the server render and the hydration pass, true after. The
 * signed-in user is only known in the browser (the persisted auth store), so
 * admin-only entries appear once mounted, or the server's HTML and the
 * client's first render would disagree.
 */
function useMounted(): boolean {
  return useSyncExternalStore(noSubscription, () => true, () => false);
}

export function SidebarNav() {
  const pathname = usePathname();
  const isAdmin = useIsAdmin();
  const mounted = useMounted();
  const showAdmin = isAdmin && mounted;
  return (
    <nav className="flex flex-col gap-5 px-3 py-3" aria-label="Main">
      {navGroups.map((group) => (
        <div key={group.label} className="flex flex-col gap-0.5">
          <p className="px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/50">
            {group.label}
          </p>
          {group.items.filter((item) => !item.adminOnly || showAdmin).map((item) => {
            const isActive = item.exact
              ? pathname === item.href
              : pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "group relative flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-150",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
                )}
              >
                {/* A bar, not just a colour change, so "where am I" doesn't rely on telling two greys apart. */}
                {isActive && (
                  <span aria-hidden className="absolute inset-y-1.5 -left-3 w-0.5 rounded-full bg-sidebar-primary" />
                )}
                <item.icon
                  className={cn(
                    "h-4 w-4 shrink-0 transition-colors",
                    isActive ? "text-sidebar-primary" : "text-sidebar-foreground/60 group-hover:text-sidebar-foreground"
                  )}
                />
                {item.label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
