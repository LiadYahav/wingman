"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { day2Api, day2Keys, keyFromParam, teamOperatorsHref } from "@/lib/day2";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/common/empty-state";
import { ChangeResultPanel, type OpenedChanges } from "@/components/addons/change-result";
import { NewOperatorForm } from "@/components/operators/new-operator-form";
import { Breadcrumbs, PageTitle, useOperatorAccess } from "@/components/operators/page-header";
import type { OperatorSummary } from "@/types/day2";

/**
 * A new operator in a team's catalog (ADR-0043, ADR-0053): the form, its
 * dry run for review, and the merge request. Beside `operators/` rather than
 * in it, so an operator named `new` keeps its page.
 */
export default function NewOperatorPage() {
  const params = useParams<{ team: string }>();
  const team = keyFromParam(params.team);
  const router = useRouter();
  const access = useOperatorAccess(team);
  const [opened, setOpened] = useState<OpenedChanges | null>(null);
  // The names a new operator cannot take (the service refuses them too, rule addon-exists).
  const operators = useQuery<OperatorSummary[]>({
    queryKey: day2Keys.operators(team),
    queryFn: () => api.get<OperatorSummary[]>(day2Api.operators(team)),
    staleTime: 60_000,
  });

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6 lg:p-8">
      <div className="space-y-2">
        <Breadcrumbs
          items={[{ label: "Operators", href: "/operators" }, { label: team, href: teamOperatorsHref(team) }, { label: "New operator" }]}
        />
        <PageTitle>New operator in {team}</PageTitle>
        <p className="text-sm text-muted-foreground">
          Adds <code>operators/&lt;name&gt;/</code> to sigs/{team} through one merge request: the operator&apos;s team default.
          Clusters get it once it is installed on them as an add-on, or made a fleet default (here or later, from its page).
        </p>
      </div>

      {opened ? (
        <div className="space-y-4">
          <ChangeResultPanel changes={opened} onDismiss={() => setOpened(null)} />
          <div className="flex flex-wrap gap-2">
            <Link href={teamOperatorsHref(team)} className={buttonVariants({ variant: "outline", size: "sm" })}>
              Back to {team}&apos;s operators
            </Link>
            <button type="button" onClick={() => setOpened(null)} className={buttonVariants({ variant: "ghost", size: "sm" })}>
              Create another
            </button>
          </div>
        </div>
      ) : !access.isAdmin ? (
        <EmptyState
          bordered
          title="Only admins add operators"
          description="Writes to a team's repo are for Wingman admins."
          action={
            <Link href={teamOperatorsHref(team)} className={buttonVariants({ variant: "outline", size: "sm" })}>
              Back to {team}&apos;s operators
            </Link>
          }
        />
      ) : (
        <NewOperatorForm
          team={team}
          existing={(operators.data ?? []).map((o) => o.name)}
          readOnlyReason={access.readOnlyReason}
          showReason={access.showReason}
          onCancel={() => router.push(teamOperatorsHref(team))}
          onOpened={(change) => setOpened({ verb: "Create", results: [change], failed: [] })}
        />
      )}
    </div>
  );
}
