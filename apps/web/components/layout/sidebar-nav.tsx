"use client";

import { usePathname } from "next/navigation";
import {
  BookOpen, Boxes, ClipboardList, GitPullRequest, Layers, LayoutDashboard, LayoutGrid, Link2, Network, Package,
  ScanSearch, Server, ServerCog, Settings, ShieldAlert, Sprout, type LucideIcon,
} from "lucide-react";
import { linksOut, type LinkOut } from "@/lib/platforms";
import type { WorkspaceId } from "@/lib/workspaces";
import { SidebarExternalLink, SidebarHeading, SidebarLink, SidebarNavList } from "./sidebar-parts";
import { usePlatforms } from "./use-platforms";
import { useWorkspace } from "./use-workspace";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
  /** The systems the team keeps apart from Wingman, after the items: their own UIs (ADR-0066). */
  linksOut?: boolean;
}

const HELP: NavGroup = {
  label: "Help",
  items: [
    { label: "Documentation", href: "/docs", icon: BookOpen },
    { label: "Settings", href: "/settings", icon: Settings },
  ],
};

/**
 * Each workspace's entries (ADR-0067). Customers: the tenants' side, all a
 * viewer ever has. Infrastructure: what serves them, an admin's.
 */
const NAV: Record<WorkspaceId, NavGroup[]> = {
  customers: [
    {
      label: "Platform",
      items: [
        { label: "Dashboard", href: "/", icon: LayoutDashboard, exact: true },
        { label: "Clusters", href: "/clusters", icon: Server },
        { label: "Flavors", href: "/specs", icon: Layers },
        { label: "Addons", href: "/addons", icon: Package },
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
    HELP,
  ],
  infrastructure: [
    {
      label: "Infrastructure",
      items: [
        { label: "Overview", href: "/infrastructure", icon: LayoutGrid, exact: true },
        { label: "Customer MCEs", href: "/mces", icon: ServerCog },
        { label: "Seeds & KV Clusters", href: "/seeds", icon: Sprout },
        { label: "Inventory Management", href: "/inventory", icon: Boxes },
      ],
    },
    { label: "Tools", items: [{ label: "Quick Links", href: "/quick-links", icon: Link2 }], linksOut: true },
    HELP,
  ],
};

const LINK_OUT_ICONS: Record<LinkOut["id"], LucideIcon> = { segments: Network, "server-scan": ScanSearch };

/** An overview is marked on itself only; every other entry on itself and below. */
function isActive(pathname: string, item: NavItem): boolean {
  return item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(item.href + "/");
}

/** The sidebar of the workspace the shell shows (`useWorkspace`). */
export function SidebarNav() {
  const pathname = usePathname();
  const workspace = useWorkspace();
  const out = linksOut(usePlatforms());
  return (
    <SidebarNavList label="Main">
      {NAV[workspace].map((group, index) => (
        <div key={group.label} className="flex flex-col gap-0.5">
          <SidebarHeading label={group.label} first={index === 0} />
          {group.items.map((item) => (
            <SidebarLink key={item.href} href={item.href} label={item.label} icon={item.icon} active={isActive(pathname, item)} />
          ))}
          {group.linksOut && out.map((link) => (
            <SidebarExternalLink key={link.id} href={link.href} label={link.label} icon={LINK_OUT_ICONS[link.id]} />
          ))}
        </div>
      ))}
    </SidebarNavList>
  );
}
