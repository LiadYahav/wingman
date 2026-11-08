"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { persistQueryClient } from "@tanstack/react-query-persist-client";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { ThemeProvider } from "next-themes";
import { useMemo, useEffect } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "sonner";

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
        // branch as it is now, not a diff cached minutes ago.
        shouldDehydrateQuery: (query) =>
          query.state.status === "success" && query.queryKey[0] !== "approvals",
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
