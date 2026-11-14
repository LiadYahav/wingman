"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { useIsAdmin } from "@/stores/auth-store";

/** The next steps: a new cluster or flavor (admins), the flavors. */
export function QuickActions() {
  const isAdmin = useIsAdmin();
  return (
    <div className="flex gap-3 flex-wrap">
      {isAdmin && (
        <Link
          href="/clusters/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors shadow-sm"
        >
          <Plus className="h-4 w-4" />New Cluster
        </Link>
      )}
      {isAdmin && (
        <Link href="/specs/new" className={buttonVariants({ variant: "outline", size: "sm" })}>
          New Flavor
        </Link>
      )}
      <Link href="/specs" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        Browse Flavors
      </Link>
    </div>
  );
}
