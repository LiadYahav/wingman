import type { ReactNode } from "react";
import { NOT_READ_TITLE, STALE_TITLE, reported } from "@/lib/server-scan/hardware";
import { isHealthSeverity } from "@/lib/server-scan/vocabulary";
import { cn } from "@/lib/utils";
import type { ComponentHealth } from "@/types/server-scan-record";
import { SeverityPill, pill } from "../server-badges";

/**
 * The server page's small parts, server-scan's (team-redbull/server-scan at
 * 92146d3: `Badge.tsx`, `Reported.tsx`, `LinkStateBadge.tsx`, the tabs'
 * `Field`, `Stat` and `Health`; decision 18) in Wingman's design.
 */

/** A tab's section heading: small, uppercase, quiet. */
export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{children}</h2>;
}

/** One labelled value of the Overview: the label small and uppercase over the value. */
export function Field({ label, children, testId }: { label: string; children: ReactNode; testId?: string }) {
  return (
    <div data-testid={testId}>
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-sm">{children}</dd>
    </div>
  );
}

/** A pill with no severity: neutral, or amber for what needs a look (Stale, Name mismatch, maintenance). */
export function Tag({ children, tone = "neutral", title }: { children: ReactNode; tone?: "neutral" | "warning"; title?: string }) {
  return (
    <span title={title} className={cn(pill, tone === "warning" ? "bg-status-warning/15 text-status-warning-fg" : "bg-muted text-foreground/80")}>
      {children}
    </span>
  );
}

const LINK_TONE: Record<string, { tone: string; dot: string }> = {
  UP: { tone: "bg-status-ready/15 text-status-ready-fg", dot: "bg-status-ready" },
  DOWN: { tone: "bg-status-error/15 text-status-error-fg", dot: "bg-status-error" },
};

/** A link's state, UP, DOWN, DISABLED or UNKNOWN, with its dot. */
export function LinkState({ state }: { state: string }) {
  const known = LINK_TONE[state] ?? { tone: "bg-muted text-muted-foreground", dot: "bg-muted-foreground/60" };
  return (
    <span className={cn(pill, known.tone)} data-testid="ss-link-state">
      <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", known.dot)} />
      {state}
    </span>
  );
}

/** A component's condition: a severity pill, the collector's own word otherwise (Cisco's UP), a dash when unread; its raw reason after it. */
export function ComponentHealthValue({ value, detail }: { value: ComponentHealth; detail?: string | null }) {
  if (value == null) return <>—</>;
  return (
    <span className="inline-flex items-center gap-1.5">
      {isHealthSeverity(value) ? <SeverityPill severity={value} /> : <span>{value}</span>}
      {detail && <span className="text-xs text-muted-foreground">({detail})</span>}
    </span>
  );
}

/** A visible "unconfirmed": real text, not only a tooltip or a fade, so every reader gets the fact. */
export function Unconfirmed() {
  return <span className="ml-1.5 align-middle text-[10px] font-medium uppercase tracking-wide text-status-warning-fg">unconfirmed</span>;
}

/**
 * A value the last collection may not have read: "Not reported" in place of
 * a zero never read, or the value carried forward, dimmed and marked
 * unconfirmed; a value that was read, as it is.
 */
export function Reported({ unread, empty, inline = false, children }: { unread: boolean; empty: boolean; inline?: boolean; children: ReactNode }) {
  const state = reported(unread, empty);
  if (state === "read") return <>{children}</>;
  const Wrapper = inline ? "span" : "div";
  if (state === "not-reported") {
    return (
      <Wrapper className={cn("text-muted-foreground", !inline && "mt-2 text-sm")} title={NOT_READ_TITLE} data-testid="ss-not-reported">
        Not reported
      </Wrapper>
    );
  }
  return (
    <Wrapper className="opacity-70" title={STALE_TITLE} data-testid="ss-unconfirmed">
      {children}
      <Unconfirmed />
    </Wrapper>
  );
}

/** A tab's empty line ("No GPUs."). */
export function Empty({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <p className="mt-2 text-sm text-muted-foreground" data-testid={testId}>
      {children}
    </p>
  );
}
