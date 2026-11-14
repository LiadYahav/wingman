"use client";

import Link from "next/link";
import { Layers, Plus } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";

/** One size and one family, as every page header's buttons: the next step primary, the rest outline. */
const PRIMARY = buttonVariants({ size: "sm" });
const SECONDARY = buttonVariants({ variant: "outline", size: "sm" });

/**
 * The title and the next steps beside it: a new cluster or flavor (admins
 * only: day1 refuses anyone else's), and the flavors.
 */
export function OverviewHeader() {
  const admin = useIsAdmin();
  const mounted = useMounted();
  // The signed-in user is known in the browser only: admin buttons appear once mounted (as the sidebar's)
  const isAdmin = admin && mounted;
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1
          className="text-2xl font-bold tracking-tight"
          style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}
        >
          Overview
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">OpenShift cluster platform at a glance</p>
      </div>
      <div className="flex flex-wrap items-center gap-2" data-testid="overview-actions">
        {isAdmin && (
          <Link href="/clusters/new" className={PRIMARY}>
            <Plus aria-hidden />New Cluster
          </Link>
        )}
        {isAdmin && (
          <Link href="/specs/new" className={SECONDARY}>
            <Plus aria-hidden />New Flavor
          </Link>
        )}
        <Link href="/specs" className={SECONDARY}>
          <Layers aria-hidden />Browse Flavors
        </Link>
      </div>
    </div>
  );
}
