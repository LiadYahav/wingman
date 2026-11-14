"use client";

import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { IntentLink } from "@/components/common/intent-link";
import { useServerScanArea } from "@/lib/api/server-scan";
import { nodeServerLink, type NodeServerLink } from "@/lib/server-scan/server-page";
import type { ServerRecord } from "@/types";

/**
 * A node's server, linked as `nodeServerLink` decides: Wingman's server page
 * in this tab (prefetched on intent, as links down a list are), or
 * server-scan's own page in a new tab.
 */
export function NodeServerAnchor({ link, className, children }: { link: NodeServerLink; className: string; children: ReactNode }) {
  if (link.inApp) {
    return (
      <IntentLink href={link.href} aria-label={link.label} className={className}>
        {children}
      </IntentLink>
    );
  }
  return (
    <a href={link.href} target="_blank" rel="noopener noreferrer" aria-label={link.label} className={className}>
      {children}
    </a>
  );
}

/** A server's name on the Nodes tab, linked; marked as leaving Wingman when it opens server-scan. */
export function NodeServerName({ server }: { server: ServerRecord }) {
  const link = nodeServerLink(server, useServerScanArea());
  return (
    <NodeServerAnchor
      link={link}
      className="group inline-flex items-center gap-1 whitespace-nowrap rounded-sm font-mono text-xs font-medium text-foreground underline-offset-4 outline-none hover:text-primary hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {server.name}
      {!link.inApp && (
        <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" aria-hidden />
      )}
    </NodeServerAnchor>
  );
}
