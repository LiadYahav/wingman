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
      maxAge: 10 * 60 * 1000, // 10 minutes
      dehydrateOptions: {
        shouldDehydrateQuery: (query) => query.state.status === "success",
      },
    });
  }, [queryClient]);

  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          {children}
          <Toaster richColors position="bottom-right" />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
