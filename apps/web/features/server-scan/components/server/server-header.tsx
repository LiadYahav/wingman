"use client";

// What it follows upstream, and at which version: docs/integrations/server-scan.yaml.

import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { CopyButton } from "@/components/data-table/copy-cell";
import { modelLine } from "@/features/server-scan/lib/hardware";
import { serverTypeLabel } from "@/features/server-scan/lib/vocabulary";
import type { ServerRecord } from "@/features/server-scan/types/server-scan-record";
import { useServersBackHref } from "./use-server-page";

/** "← Servers", back to the Servers view the page was opened from (server-scan's "← Back to inventory"). */
export function BackToServers() {
  return (
    <Link href={useServersBackHref()} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" data-testid="ss-back">
      <ArrowLeft aria-hidden className="h-3.5 w-3.5" />
      Servers
    </Link>
  );
}

/**
 * Opens the BMC's own web console in a new tab (`https://`, the one scheme
 * every vendor's BMC serves), its address first on hover (server-scan
 * v6.2.0); nothing for a server whose BMC host was not read.
 */
function BmcButton({ host, name }: { host: string | null; name: string }) {
  if (!host) return null;
  const label = `Open BMC console for ${name}`;
  return (
    <a
      href={`https://${host}`}
      target="_blank"
      rel="noopener noreferrer"
      title={`${host} — open BMC console`}
      aria-label={label}
      className="inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium text-muted-foreground outline-none transition-colors hover:border-foreground/30 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
    >
      <ExternalLink aria-hidden className="h-3.5 w-3.5" />
      BMC
    </a>
  );
}

/**
 * server-scan's header: the name with its copy button, the BMC console, the
 * model under them, and whether it is a physical server or a VM (v6.3.0's
 * `server_type`), beside the model in one muted line.
 */
export function ServerHeader({ record }: { record: ServerRecord }) {
  return (
    <header className="space-y-1">
      <BackToServers />
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex min-w-0 items-center gap-1">
          <h1 className="truncate text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
            {record.name}
          </h1>
          <CopyButton value={record.name} label="server name" />
        </div>
        <BmcButton host={record.network.bmc.host} name={record.name} />
      </div>
      <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-muted-foreground">
        <span data-testid="ss-server-model">{modelLine(record.model, record.hardware.gpus)}</span>
        <span aria-hidden>·</span>
        <span data-testid="ss-server-type">{serverTypeLabel(record.server_type)}</span>
      </p>
    </header>
  );
}
