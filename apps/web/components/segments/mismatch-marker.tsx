"use client";

import Link from "next/link";
import { TriangleAlert } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { clusterHref } from "@/lib/clusters";
import type { Segment } from "@/types/segments";

/**
 * A row's mark where segments-manager disagrees with a cluster file (ADR-0039's
 * checks, from the segment's side). It opens the sentences, each under the
 * cluster file it is about. Git stays the source of truth: nothing here fixes
 * anything.
 */
export function MismatchMarker({ segment }: { segment: Segment }) {
  const count = segment.mismatches.length;
  if (count === 0) return null;
  const label = `${count} disagreement${count === 1 ? "" : "s"} with the cluster file`;
  return (
    <Popover>
      <PopoverTrigger
        aria-label={label}
        title={label}
        data-testid="segment-mismatch"
        className="inline-flex shrink-0 items-center rounded p-0.5 text-status-warning outline-none transition-colors hover:bg-status-warning/15 focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <TriangleAlert aria-hidden className="h-3.5 w-3.5" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 gap-2" aria-label="Disagrees with the cluster file">
        <p className="text-xs font-medium">segments-manager disagrees with the cluster file</p>
        <ul className="space-y-1.5" data-testid="segment-mismatches">
          {segment.mismatches.map((m) => (
            <li key={`${m.cluster}:${m.detail}`} className="text-xs">
              <Link href={clusterHref({ name: m.cluster, site: m.site, mce: m.mce })} className="font-mono text-primary hover:underline">
                {m.cluster}
              </Link>
              <span className="block text-muted-foreground">{m.detail}</span>
            </li>
          ))}
        </ul>
        <p className="text-[11px] text-muted-foreground">Git is the source of truth: the file is what the cluster runs with.</p>
      </PopoverContent>
    </Popover>
  );
}
