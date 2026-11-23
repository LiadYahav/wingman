import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import type { ServerRecord } from "@/types";

/**
 * A node's server, linked to its page in server-scan's own UI (`url`, built
 * by day1), in a new tab: the team keeps server-scan apart from Wingman
 * (ADR-0066).
 */
export function NodeServerAnchor({
  server,
  className,
  children,
}: {
  server: Pick<ServerRecord, "name" | "url">;
  className: string;
  children: ReactNode;
}) {
  return (
    <a
      href={server.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${server.name}, its server-scan page (opens in a new tab)`}
      className={className}
    >
      {children}
    </a>
  );
}

/** A server's name on the Nodes tab, linked to server-scan and marked as leaving Wingman. */
export function NodeServerName({ server }: { server: ServerRecord }) {
  return (
    <NodeServerAnchor
      server={server}
      className="group inline-flex items-center gap-1 whitespace-nowrap rounded-sm font-mono text-xs font-medium text-foreground underline-offset-4 outline-none hover:text-primary hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {server.name}
      <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" aria-hidden />
    </NodeServerAnchor>
  );
}
