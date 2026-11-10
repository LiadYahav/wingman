"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FlavorEditor } from "@/components/specs/flavor-editor/flavor-editor";
import { newDraft } from "@/components/specs/flavor-editor/model";
import { defaultConfigs, useMachineConfigs } from "@/lib/machine-configs";
import { useIsAdmin } from "@/stores/auth-store";

/** A new flavor; its first nodepool starts from the nodepool defaults, so it waits for them. */
export default function NewSpecPage() {
  const isAdmin = useIsAdmin();
  const { data: catalog, isLoading } = useMachineConfigs(isAdmin);

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-32 text-center">
        <p className="text-lg font-semibold">Insufficient permissions</p>
        <p className="text-sm text-muted-foreground">Your role (viewer) does not have access to create flavors.</p>
        <Link href="/specs" className={buttonVariants({ variant: "outline", size: "sm" })}>
          Back to flavors
        </Link>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 lg:px-8" aria-busy>
        <Skeleton className="h-10 w-64 rounded-lg" />
        <Skeleton className="h-12 rounded-lg" />
        <Skeleton className="h-80 rounded-2xl" />
      </div>
    );
  }

  // A catalogue that could not be read gives no defaults; the editor says why.
  return <FlavorEditor initial={newDraft(defaultConfigs(catalog))} />;
}
