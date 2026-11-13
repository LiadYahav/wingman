"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, Copy, ExternalLink, Network } from "lucide-react";
import { useSegmentsArea } from "@/lib/api/segments";
import { clusterSegmentsLink } from "@/lib/segments/links";
import { cn } from "@/lib/utils";
import type { SegmentsManagerLinks } from "@/types";

/** Copies `text`; the icon turns to a check for a moment, and a screen reader hears it. */
function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const timer = setTimeout(() => setState("idle"), 1500);
    return () => clearTimeout(timer);
  }, [state]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      // No clipboard (not a secure context, or denied): the name stays selectable
      setState("failed");
    }
  };
  const Icon = state === "copied" ? Check : Copy;
  return (
    <>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={label}
        title={state === "failed" ? "Could not copy: select the name instead" : label}
        className="rounded p-0.5 text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <Icon className={cn("h-3.5 w-3.5", state === "copied" && "text-status-ready-fg")} aria-hidden />
      </button>
      <span role="status" className="sr-only">
        {state === "copied" ? "Copied" : state === "failed" ? "Could not copy" : ""}
      </span>
    </>
  );
}

/**
 * segments-manager's UI opens no single cluster, so this link opens the UI and
 * names what to search for there: the file stem, its `cluster_name`. Day1
 * builds both URLs (`segments_manager`); the page only shows them.
 */
function SegmentsManagerLink({ name, url, searchUrl }: { name: string; url: string; searchUrl: string }) {
  return (
    <div data-testid="segments-manager" className="pt-2 border-t border-border/50 space-y-1">
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="group inline-flex items-center gap-1 font-medium hover:text-primary transition-colors"
      >
        Segments Manager
        <ExternalLink className="h-3 w-3 shrink-0 opacity-60 group-hover:opacity-100" aria-hidden />
      </a>
      <p className="flex flex-wrap items-center gap-x-1 text-xs text-muted-foreground">
        search for <span data-testid="segments-manager-search" className="font-mono text-foreground break-all">{name}</span>
        <CopyButton text={name} label={`Copy ${name}`} />
      </p>
      <a
        href={searchUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="group inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary transition-colors"
      >
        this cluster&apos;s segment (JSON)
        <ExternalLink className="h-3 w-3 shrink-0 opacity-60 group-hover:opacity-100" aria-hidden />
      </a>
    </div>
  );
}

/**
 * The HostedCluster card's link to the cluster's segments, chosen by the one
 * helper (`lib/segments/links.ts`): Wingman's Segments area filtered to the
 * cluster for an admin who has it, segments-manager's UI for anyone else,
 * nothing when segments-manager is not configured.
 */
export function ClusterSegmentsLink({ name, external }: { name: string; external: SegmentsManagerLinks | null }) {
  const link = clusterSegmentsLink(name, { area: useSegmentsArea(), external });
  if (!link) return null;
  if (link.kind === "external") return <SegmentsManagerLink name={name} url={link.url} searchUrl={link.searchUrl} />;
  return (
    <div data-testid="cluster-segments" className="pt-2 border-t border-border/50">
      <Link href={link.href} className="group inline-flex items-center gap-1.5 font-medium transition-colors hover:text-primary">
        <Network aria-hidden className="h-3.5 w-3.5 text-muted-foreground group-hover:text-primary" />
        This cluster&apos;s segments
      </Link>
    </div>
  );
}
