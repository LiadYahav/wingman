"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ServerOff } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { ProblemList } from "@/components/common/problem-list";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isApiError } from "@/lib/api-client";
import { useServerScanRecord } from "@/lib/api/server-scan";
import { SERVERS_HREF, SERVER_TABS, TAB_LABELS, parseTab } from "@/lib/server-scan/server-page";
import type { ServerRecord } from "@/types/server-scan-record";
import { Blocked, isBlocked } from "../blocked";
import { HardwareTab } from "./hardware-tab";
import { HistoryTab } from "./history-tab";
import { ConnectivityTab, NetworkTab } from "./network-tab";
import { OverviewTab } from "./overview-tab";
import { BackToServers, ServerHeader } from "./server-header";
import { useServerTab } from "./use-server-page";

/** The route's id, as the browser sent it (an id with `/` or a space arrives encoded). */
function decodedId(raw: string | string[] | undefined): string {
  const value = Array.isArray(raw) ? (raw[0] ?? "") : (raw ?? "");
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function Loading() {
  return (
    <div className="space-y-4" aria-busy="true" data-testid="ss-server-loading">
      <Skeleton className="h-8 w-96 max-w-full" />
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-8 w-80" />
      <div className="grid gap-4 rounded-xl border bg-card p-5 sm:grid-cols-2">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    </div>
  );
}

/** The five tabs, the one shown in the URL; only the shown one is rendered (History reads when shown). */
function ServerTabs({ record }: { record: ServerRecord }) {
  const [tab, setTab] = useServerTab();
  return (
    <Tabs value={tab} onValueChange={(value) => setTab(parseTab(String(value)))}>
      <TabsList aria-label="Server detail tabs">
        {SERVER_TABS.map((id) => (
          <TabsTrigger key={id} value={id} data-testid={`ss-tab-${id}`}>
            {TAB_LABELS[id]}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="overview" className="mt-4">
        <OverviewTab record={record} />
      </TabsContent>
      <TabsContent value="hardware" className="mt-4">
        <HardwareTab hardware={record.hardware} unreadFields={record.unread_fields} />
      </TabsContent>
      <TabsContent value="network" className="mt-4">
        <NetworkTab network={record.network} osNames={record.nic_os_names} unreadFields={record.unread_fields} />
      </TabsContent>
      <TabsContent value="connectivity" className="mt-4">
        <ConnectivityTab connectivity={record.connectivity} />
      </TabsContent>
      <TabsContent value="history" className="mt-4">
        {tab === "history" && <HistoryTab record={record} />}
      </TabsContent>
    </Tabs>
  );
}

/** Why there is no record to show: not an admin or not set up, no such server, or server-scan failing. */
function NoRecord({ id, error }: { id: string; error: unknown }) {
  if (isBlocked(error)) return <Blocked error={error} />;
  if (isApiError(error, "NOT_FOUND")) {
    return (
      <EmptyState
        icon={ServerOff}
        bordered
        title={`No server ${id}`}
        description="server-scan has no server with this id: it may have been pruned, or the link is wrong."
        action={
          <Link href={SERVERS_HREF} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Servers
          </Link>
        }
        data-testid="ss-server-not-found"
      />
    );
  }
  return <ProblemList error={error} title="The server could not be loaded from server-scan" />;
}

/**
 * The Server Scan area's third page (ADR-0048's 3.25.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §9): server-scan's server
 * page, one server's record in five tabs, in Wingman's design. Read on open
 * and again when opened after 30 seconds, as the original; never polled.
 */
export function ServerPage() {
  const id = decodedId(useParams<{ id: string }>().id);
  const record = useServerScanRecord(id);
  const data = isBlocked(record.error) ? undefined : record.data;
  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6 lg:p-8">
      {record.isPending ? (
        <Loading />
      ) : !data ? (
        <div className="space-y-4">
          <BackToServers />
          <NoRecord id={id} error={record.error} />
        </div>
      ) : (
        <>
          <ServerHeader record={data} />
          {record.error !== null && <ProblemList error={record.error} title="The last read failed; this is the record read before it" />}
          <ServerTabs record={data} />
        </>
      )}
    </div>
  );
}
