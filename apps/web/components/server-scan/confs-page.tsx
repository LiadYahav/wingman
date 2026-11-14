"use client";

import { useState } from "react";
import { Info, PackageOpen, Search } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { Hint } from "@/components/common/hint";
import { ProblemList } from "@/components/common/problem-list";
import { Skeleton } from "@/components/ui/skeleton";
import { useServerScanConfs } from "@/lib/api/server-scan";
import { confsCount, unreadableNotice, visibleConfs } from "@/lib/server-scan/confs";
import type { ConfList } from "@/types/server-scan-confs";
import { Blocked, isBlocked } from "./blocked";
import { ConfsTable } from "./confs-table";

const READ_ONLY =
  "Read only: another system writes server-scan's confs collection, and server-scan and Wingman only read it. A conf is not linked to the servers built to it.";

function Loading() {
  return (
    <div className="space-y-2 rounded-xl border bg-card p-3" aria-busy="true" data-testid="ss-confs-loading">
      {Array.from({ length: 8 }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

/** server-scan's notice naming the stored confs it could not read. */
function Unreadable({ ids }: { ids: string[] }) {
  const notice = unreadableNotice(ids);
  if (!notice) return null;
  return (
    <p className="rounded-lg border border-status-warning/40 bg-status-warning/10 p-3 text-sm text-status-warning-fg" data-testid="ss-confs-unreadable">
      {notice} <span className="font-mono">{ids.join(", ")}</span>
    </p>
  );
}

function SearchBox({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="flex w-full flex-col gap-1 text-xs font-medium text-muted-foreground sm:w-96">
      <span>Search</span>
      <span className="relative">
        <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2" />
        <input
          type="search"
          value={value}
          placeholder="Conf ID, part number, model, CPU, GPU or disk type"
          title="Every word must appear in the conf's id, part number, model, CPU, memory or disk type, or GPU model"
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape" && value) onChange("");
          }}
          className="h-8 w-full rounded-lg border bg-card pl-8 pr-2 text-sm font-normal text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 [&::-webkit-search-cancel-button]:hidden"
        />
      </span>
    </label>
  );
}

function Catalog({ data }: { data: ConfList }) {
  const [search, setSearch] = useState("");
  if (data.items.length === 0) {
    return (
      <div className="space-y-4">
        <Unreadable ids={data.unreadable} />
        <EmptyState
          icon={PackageOpen}
          bordered
          title="No confs are stored."
          description="server-scan's confs collection is empty. Another system writes it."
          data-testid="ss-confs-empty"
        />
      </div>
    );
  }
  const rows = visibleConfs(data.items, search);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <SearchBox value={search} onChange={setSearch} />
        <p className="pb-1.5 text-sm text-muted-foreground" aria-live="polite" data-testid="ss-confs-count">
          {confsCount(rows.length, data.items.length)}
        </p>
      </div>
      <Unreadable ids={data.unreadable} />
      <ConfsTable rows={rows} empty="No conf matches the search." />
    </div>
  );
}

/**
 * The Server Scan area's Confs page (ADR-0048's 3.29.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §10): server-scan's hardware
 * catalog, its search, columns, words and opened rows, in Wingman's design.
 * Read only. Read on open and again when opened after 30 seconds, as the
 * original; never polled.
 */
export function ConfsPage() {
  const confs = useServerScanConfs();
  const blocked = isBlocked(confs.error);
  const data = blocked ? undefined : confs.data;
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6 lg:p-8">
      <header>
        <div className="flex items-center gap-1">
          <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            Confs
          </h1>
          <Hint hint={READ_ONLY} label="About Confs" testId="ss-confs-about">
            <Info aria-hidden className="h-4 w-4 text-muted-foreground" />
          </Hint>
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">Server configurations (specs). Click a row for the full spec.</p>
      </header>
      {blocked ? (
        <Blocked error={confs.error} />
      ) : confs.isPending ? (
        <Loading />
      ) : !data ? (
        <ProblemList error={confs.error} title="The confs could not be loaded from server-scan" />
      ) : (
        <>
          {confs.error !== null && <ProblemList error={confs.error} title="The last read failed; this is the read before it" />}
          <Catalog data={data} />
        </>
      )}
    </div>
  );
}
