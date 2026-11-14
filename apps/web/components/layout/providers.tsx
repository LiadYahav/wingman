"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { persistQueryClient } from "@tanstack/react-query-persist-client";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { ThemeProvider } from "next-themes";
import { useMemo, useEffect } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "sonner";

/** Queries never restored from localStorage: what they show must be read now. */
const NOT_PERSISTED = new Set(["approvals", "placement"]);
/**
 * Never kept in localStorage at all: server-scan's fleet rows (2 MB for ~3,100
 * servers, polled every 30 s) would not fit, and the browser's HTTP cache
 * already makes re-reading an unchanged fleet a bodiless 304; nor its
 * architecture diagrams (about 0.7 MB each); nor its Jobs and their logs (a
 * run's state is now or nothing: a stored one would offer Run job while a
 * run goes on).
 */
const NEVER_STORED = new Set(["servers", "architecture", "jobs"]);
const TOO_BIG = (key: readonly unknown[]) => key[0] === "server-scan" && NEVER_STORED.has(String(key[1]));

export function Providers({ children }: { children: React.ReactNode }) {
  // Create QueryClient once - must be stable across renders
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 2 * 60 * 1000,   // 2 min — data considered fresh, no refetch
            gcTime: 10 * 60 * 1000,     // 10 min garbage collection
            retry: 2,
            refetchOnWindowFocus: false,
          },
        },
      }),
    []
  );

  // Set up persistence on client side only
  useEffect(() => {
    const persister = createSyncStoragePersister({
      storage: window.localStorage,
      key: "wingman-query-cache",
    });

    persistQueryClient({
      queryClient,
      persister,
      // A new build drops what an older one cached (its shapes may differ)
      buster: process.env.WINGMAN_WEB_BUILD,
      maxAge: 10 * 60 * 1000, // 10 minutes
      dehydrateOptions: {
        // An approval's detail is what the reviewer approves (its sha), so it is
        // never restored from storage: a page opened later always shows the
        // branch as it is now, not a diff cached minutes ago. An MCE placement
        // is the MCEs' free pods now (ADR-0050), never minutes-old numbers.
        shouldDehydrateQuery: (query) =>
          query.state.status === "success" && !NOT_PERSISTED.has(String(query.queryKey[0])) && !TOO_BIG(query.queryKey),
      },
    });
  }, [queryClient]);

  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          {children}
          <Toaster richColors position="bottom-right" />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
