"use client";

import { Lock } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";

/**
 * An Infrastructure page (ADR-0067): its content for an admin only. A
 * viewer, who never knows of the MCEs, seeds or the inventory, is told the
 * page is an admin's and nothing is read for them; before the role is known
 * (the server's render) a placeholder stands where the page goes.
 */
export function AdminsOnly({ children }: { children: React.ReactNode }) {
  const admin = useIsAdmin();
  const mounted = useMounted();
  if (!mounted) {
    return (
      <div className="p-6 lg:p-8 max-w-6xl mx-auto space-y-4" aria-busy="true">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }
  if (!admin) {
    return (
      <div className="p-6 lg:p-8 max-w-6xl mx-auto">
        <EmptyState
          icon={Lock}
          bordered
          title="For admins"
          description="This page is in the Infrastructure workspace, which only Wingman's admins see: the MCEs, seeds, KV clusters and servers behind the customers' clusters."
          data-testid="admins-only"
        />
      </div>
    );
  }
  return children;
}
