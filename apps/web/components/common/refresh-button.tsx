"use client";

import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** A list page's Refresh: reads every query under `queryKey` again, spinning while `fetching`. */
export function RefreshButton({ queryKey, fetching, title }: { queryKey: QueryKey; fetching: boolean; title: string }) {
  const queryClient = useQueryClient();
  return (
    <button
      onClick={() => queryClient.invalidateQueries({ queryKey })}
      disabled={fetching}
      className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1.5")}
      title={title}
    >
      <RefreshCw className={cn("h-3.5 w-3.5", fetching && "animate-spin")} />
      Refresh
    </button>
  );
}
