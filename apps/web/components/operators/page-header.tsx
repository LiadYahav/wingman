"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useIsAdmin } from "@/stores/auth-store";
import { useTeamAccess } from "@/components/addons/team-access";

/** Where an Operators page sits: Operators › team › operator. */
export function Breadcrumbs({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground">
      <ol className="flex flex-wrap items-center gap-1">
        {items.map((item, i) => (
          <li key={`${item.label}|${i}`} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3 w-3" aria-hidden />}
            {item.href ? (
              <Link href={item.href} className="hover:text-foreground hover:underline">
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="font-medium text-foreground">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function PageTitle({ children }: { children: React.ReactNode }) {
  return (
    <h1 className="break-words text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading, var(--font-sans))" }}>
      {children}
    </h1>
  );
}

/**
 * Whether the viewer may write to `team`'s operators, and why not (ADR-0043,
 * ADR-0053). Fails closed: the teams list must say the team is writable, and
 * so must the read itself when it says (`also`). Writes are admin-only.
 */
export function useOperatorAccess(team: string, also?: { writable: boolean; read_only_reason: string | null }) {
  const isAdmin = useIsAdmin();
  const access = useTeamAccess(team);
  const reason = !access.writable
    ? access.reason
    : also && !also.writable
      ? (also.read_only_reason ?? `${team} is read-only in Wingman.`)
      : null;
  return {
    isAdmin,
    /** Why writes are off, or `null`. */
    readOnlyReason: reason,
    /** Show the reason (held back while the teams list loads, so it does not flash). */
    showReason: Boolean(reason) && !access.pending,
  };
}
