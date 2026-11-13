"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ProblemList } from "@/components/common/problem-list";
import { FlavorEditor } from "@/components/specs/flavor-editor/flavor-editor";
import { draftFromSpec } from "@/components/specs/flavor-editor/model";
import { useIsAdmin } from "@/stores/auth-store";
import type { SpecDetail } from "@/types";

/**
 * Edit a flavor. The update sends the `last_commit_id` this page read the
 * flavor at, so the editor opens only on a read made for this visit (never
 * on a cached copy), and a reload starts it again from a new read.
 */
export default function EditSpecPage() {
  const params = useParams();
  const name = params.name as string;
  const isAdmin = useIsAdmin();
  // Bumped by a reload: the editor starts over from the flavor read again.
  const [generation, setGeneration] = useState(0);

  const { data: spec, error, isFetchedAfterMount, refetch } = useQuery<SpecDetail>({
    queryKey: day1Keys.specs.one(name),
    queryFn: () => day1Api.specs.get(name),
    staleTime: 60_000,
    refetchOnMount: "always",
    retry: (count, e) => !isApiError(e, "VALIDATION_ERROR") && !isApiError(e, "NOT_FOUND") && count < 2,
  });

  const reload = async () => {
    await refetch();
    setGeneration((g) => g + 1);
  };

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-32 text-center">
        <p className="text-lg font-semibold">Insufficient permissions</p>
        <p className="text-sm text-muted-foreground">Your role (viewer) does not have access to edit flavors.</p>
        <Link href={`/specs/${encodeURIComponent(name)}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
          Back to the flavor
        </Link>
      </div>
    );
  }

  if (error && !spec) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <Link href={`/specs/${encodeURIComponent(name)}`} className={buttonVariants({ variant: "ghost", size: "icon" })} aria-label="Back to the flavor">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="min-w-0 break-all text-2xl font-semibold tracking-[-0.02em]">Edit Flavor {name}</h1>
        </div>
        <ProblemList
          error={error}
          title={
            isApiError(error, "VALIDATION_ERROR")
              ? "This flavor's file does not load, so it cannot be edited here. Fix it in GitLab, or delete the flavor."
              : undefined
          }
        />
      </div>
    );
  }

  if (!spec || !isFetchedAfterMount) {
    return (
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 lg:px-8" aria-busy>
        <Skeleton className="h-10 w-64 rounded-lg" />
        <Skeleton className="h-12 rounded-lg" />
        <Skeleton className="h-80 rounded-2xl" />
        <Skeleton className="h-80 rounded-2xl" />
      </div>
    );
  }

  return <FlavorEditor key={generation} spec={spec} initial={draftFromSpec(spec)} onReload={reload} />;
}
