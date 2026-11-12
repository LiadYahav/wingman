"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys, teamAddonsHref } from "@/lib/day2";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { ChangeResultPanel, type OpenedChanges } from "@/components/addons/change-result";
import { NewAddonForm } from "@/components/addons/new-addon-form";
import { Breadcrumbs, PageTitle, useAddonAccess } from "@/components/addons/page-header";
import type { AddonSummary } from "@/types/day2";

function BackLink({ team }: { team: string }) {
  return (
    <Link href={teamAddonsHref(team)} className={buttonVariants({ variant: "outline", size: "sm" })}>
      Back to {team}&apos;s add-ons
    </Link>
  );
}

function NewAddon({ team }: { team: string }) {
  const router = useRouter();
  const access = useAddonAccess(team);
  const [opened, setOpened] = useState<OpenedChanges | null>(null);
  // The names a new add-on cannot take (the service refuses them too, rule addon-exists).
  const existing = useQuery<AddonSummary[]>({
    queryKey: day2Keys.teamAddons(team),
    queryFn: () => api.get<AddonSummary[]>(day2Api.teamAddons(team)),
    staleTime: 60_000,
  });

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6 lg:p-8">
      <div className="space-y-2">
        <Breadcrumbs items={[{ label: "Addons", href: "/addons" }, { label: team, href: teamAddonsHref(team) }, { label: "New add-on" }]} />
        <PageTitle>New add-on in {team}</PageTitle>
        <p className="text-sm text-muted-foreground">
          Adds <code>operators/&lt;name&gt;/</code> to sigs/{team} through one merge request: the add-on&apos;s team default.
          Clusters get it once it is installed on them, or made a fleet default (here or later, from its page).
        </p>
      </div>

      {opened ? (
        <div className="space-y-4">
          <ChangeResultPanel changes={opened} onDismiss={() => setOpened(null)} />
          <div className="flex flex-wrap gap-2">
            <BackLink team={team} />
            <button type="button" onClick={() => setOpened(null)} className={buttonVariants({ variant: "ghost", size: "sm" })}>
              Create another
            </button>
          </div>
        </div>
      ) : !access.isAdmin ? (
        <EmptyState
          bordered
          title="Only admins add add-ons"
          description="Writes to a team's repo are for Wingman admins."
          action={<BackLink team={team} />}
        />
      ) : (
        <NewAddonForm
          team={team}
          existing={(existing.data ?? []).map((o) => o.name)}
          readOnlyReason={access.readOnlyReason}
          showReason={access.showReason}
          onCancel={() => router.push(teamAddonsHref(team))}
          onOpened={(change) => setOpened({ verb: "Create", results: [change], failed: [] })}
        />
      )}
    </div>
  );
}

function NewAddonForTeam() {
  const team = useSearchParams().get("team");
  if (!team) {
    return (
      <div className="mx-auto max-w-3xl p-6 lg:p-8">
        <EmptyState
          bordered
          title="Which team's add-on?"
          description="A new add-on goes into one team's repo: start it from that team on the Addons page."
          action={
            <Link href="/addons" className={buttonVariants({ variant: "outline", size: "sm" })}>
              Addons
            </Link>
          }
        />
      </div>
    );
  }
  return <NewAddon key={team} team={team} />;
}

/**
 * A new add-on in a team's catalog (ADR-0043, ADR-0053), started from the
 * team's section of the Addons page: the form, its dry run for review, and the
 * merge request. The team is a query (`?team=`), so an add-on named `new`
 * keeps its own page at `/addons/<team>/new`.
 */
export default function NewAddonPage() {
  return (
    <Suspense fallback={<Skeleton className="m-6 h-64 rounded-xl" />}>
      <NewAddonForTeam />
    </Suspense>
  );
}
