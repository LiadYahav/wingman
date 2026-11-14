"use client";

import type { ReactNode } from "react";
import { IntentLink } from "@/components/common/intent-link";
import { serverHref } from "@/lib/server-scan/server-page";
import { cn } from "@/lib/utils";
import { rememberServersView } from "./server/use-server-page";

/**
 * A link to a server's page in the Server Scan area, the one view of a server
 * (docs/notes/2026-11-13-server-scan-area-api.md §9.8). It prefetches on
 * intent only, as links down a list do. `fromServers`: followed from the
 * Servers page, whose view (its filters) "← Servers" then returns to.
 * `newTab`: opens beside what is open (the install dialog's picker keeps its
 * choice).
 */
export function ServerLink({
  id,
  children,
  fromServers = false,
  newTab = false,
  className,
}: {
  id: string;
  children: ReactNode;
  fromServers?: boolean;
  newTab?: boolean;
  className?: string;
}) {
  const style = cn("text-primary underline-offset-2 outline-none hover:underline focus-visible:underline", className);
  if (newTab) {
    return (
      <a href={serverHref(id)} target="_blank" rel="noopener noreferrer" className={style} data-testid="ss-server-link">
        {children}
      </a>
    );
  }
  return (
    <IntentLink
      href={serverHref(id)}
      className={style}
      data-testid="ss-server-link"
      onClick={fromServers ? () => rememberServersView(`${window.location.pathname}${window.location.search}`) : undefined}
    >
      {children}
    </IntentLink>
  );
}
