"use client";

import Link from "next/link";
import { Building2, Users, type LucideIcon } from "lucide-react";
import { useMounted } from "@/hooks/use-mounted";
import { cn } from "@/lib/utils";
import { WORKSPACES, type WorkspaceId } from "@/lib/workspaces";
import { useIsAdmin } from "@/stores/auth-store";
import { useWorkspace } from "./use-workspace";

const ICONS: Record<WorkspaceId, LucideIcon> = { customers: Users, infrastructure: Building2 };

const ENTRY =
  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] font-medium outline-none transition-[color,background-color,box-shadow,transform] duration-150 focus-visible:ring-2 focus-visible:ring-ring/50 motion-safe:active:scale-[0.97]";

/**
 * The top bar's switch between the two workspaces (ADR-0067): Customers,
 * the tenants' side, and Infrastructure, what serves them. Each goes to its
 * workspace's home; the one you are in is marked. Admins only: a viewer is
 * always in Customers and has nothing to switch to, so it is not drawn (nor
 * before the role is known, as the sidebar's admin entries).
 */
export function WorkspaceSwitch() {
  const admin = useIsAdmin();
  const mounted = useMounted();
  const current = useWorkspace();
  if (!admin || !mounted) return null;
  return (
    <nav aria-label="Workspace" className="inline-flex items-center gap-0.5 rounded-lg bg-muted p-0.5">
      {WORKSPACES.map((workspace) => {
        const Icon = ICONS[workspace.id];
        const active = workspace.id === current;
        return (
          <Link
            key={workspace.id}
            href={workspace.href}
            title={workspace.description}
            aria-current={active ? "true" : undefined}
            data-workspace={workspace.id}
            className={cn(
              ENTRY,
              active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon aria-hidden className={cn("h-3.5 w-3.5", active && "text-primary")} />
            {workspace.label}
          </Link>
        );
      })}
    </nav>
  );
}
