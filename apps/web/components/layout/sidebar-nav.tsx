"use client";

import { usePathname } from "next/navigation";
import { LayoutDashboard, Server, Package, GitPullRequest, ClipboardList, Settings, Layers, BookOpen, ShieldAlert, Link2, Boxes, type LucideIcon } from "lucide-react";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";
import { SidebarHeading, SidebarLink, SidebarNavList } from "./sidebar-parts";

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
      { label: "Inventory Management", href: "/inventory", icon: Boxes },
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

/** Dashboard is marked on itself only; every other entry on itself and below. */
function isActive(pathname: string, item: NavItem): boolean {
  return item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(item.href + "/");
}

export function SidebarNav() {
  const pathname = usePathname();
  const isAdmin = useIsAdmin();
  const mounted = useMounted();
  const showAdmin = isAdmin && mounted;
  return (
    <SidebarNavList label="Main">
      {navGroups.map((group, index) => (
        <div key={group.label} className="flex flex-col gap-0.5">
          <SidebarHeading label={group.label} first={index === 0} />
          {group.items.filter((item) => !item.adminOnly || showAdmin).map((item) => (
            <SidebarLink key={item.href} href={item.href} label={item.label} icon={item.icon} active={isActive(pathname, item)} />
          ))}
        </div>
      ))}
    </SidebarNavList>
  );
}
