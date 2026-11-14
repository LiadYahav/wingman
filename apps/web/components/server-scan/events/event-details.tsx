import { Fragment } from "react";
import { actorLabel, type ActorKind } from "@/lib/server-scan/actor";
import {
  describeEvent, healthSections, matchedRule, topReason, transition, transitionSides, visibleData, type EventReason, type EventTone,
} from "@/lib/server-scan/events";
import { cn } from "@/lib/utils";
import type { AuditEvent } from "@/types/server-scan-record";
import { pill, severityTone } from "../server-badges";

/**
 * One audit event's parts, as server-scan's `EventTimeline.tsx`
 * (team-redbull/server-scan at 92146d3, decision 18) shows them: the type's
 * tinted pill, a status change's FROM → TO, the actor with its kind, and the
 * details a row opens. The words are `lib/server-scan/events.ts`.
 */

const EVENT_TONE: Record<EventTone, string> = {
  warning: "bg-status-warning/15 text-status-warning-fg",
  maintenance: "bg-status-provisioning/15 text-status-provisioning-fg",
  critical: "bg-status-error/15 text-status-error-fg",
  major: "bg-status-error/10 text-status-error-fg",
  info: "bg-primary/12 text-primary",
  healthy: "bg-status-ready/15 text-status-ready-fg",
  neutral: "bg-muted text-foreground/80",
};

export function eventToneClass(tone: EventTone): string {
  return EVENT_TONE[tone];
}

/** A severity as server-scan wrote it (`CRITICAL`), in its colour. */
function SeverityChip({ severity }: { severity: string }) {
  return <span className={cn(pill, severityTone(severity))}>{severity}</span>;
}

/** FROM → TO under the type: severity chips for a health change, plain words for the others. */
export function Transition({ event }: { event: AuditEvent }) {
  const sides = transitionSides(event.data);
  if (!sides) return null;
  const [from, to] = sides;
  if (event.event_type !== "HEALTH_CHANGED") {
    return <div className="mt-1 text-xs text-muted-foreground">{`${from} → ${to}`}</div>;
  }
  return (
    <div className="mt-1">
      <span role="group" aria-label={`${from} → ${to}`} className="inline-flex items-center gap-1.5">
        <SeverityChip severity={from} />
        <span aria-hidden>→</span>
        <SeverityChip severity={to} />
      </span>
    </div>
  );
}

const KIND_TONE: Record<ActorKind, string> = {
  user: "bg-primary/12 text-primary",
  token: "bg-status-error/10 text-status-error-fg",
  system: "bg-muted text-muted-foreground",
};

/** Who: the actor's name, and whether it is a person, a token or the system. */
export function ActorCell({ actor }: { actor: AuditEvent["actor"] }) {
  const { label, kind } = actorLabel(actor);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span>{label}</span>
      <span className={cn(pill, "px-1.5 text-[0.7rem]", KIND_TONE[kind])}>{kind}</span>
    </span>
  );
}

const REASON_FIELDS = ["Policy key", "Policy name", "Category", "Severity", "Message"] as const;

/** One reason, every field labelled; a missing value is a dash. */
function ReasonBlock({ reason }: { reason: EventReason }) {
  const values = [reason.policy_key, reason.policy_name, reason.category, reason.severity, reason.message];
  return (
    <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-0.5 rounded-md border px-2 py-1">
      {REASON_FIELDS.map((label, i) => (
        <Fragment key={label}>
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-words">{label === "Severity" && values[i] ? <SeverityChip severity={values[i]} /> : (values[i] ?? "—")}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

/** One side of a health change: its severity and only its worst reason (the rest are in the JSON). */
function HealthSide({ label, severity, reasons }: { label: "FROM" | "TO"; severity: string; reasons: EventReason[] }) {
  const top = topReason(reasons);
  return (
    <section aria-label={label} className="space-y-1">
      <div className="flex items-center gap-1.5 font-medium text-muted-foreground">
        <span>{label}</span>
        <SeverityChip severity={severity} />
      </div>
      {top === null ? <div className="text-muted-foreground">nothing failing</div> : <ReasonBlock reason={top} />}
    </section>
  );
}

function HealthWhy({ data }: { data: Record<string, unknown> }) {
  const { from, to } = healthSections(data);
  if (from === null && to === null) return null;
  const [fromSeverity = "?", toSeverity = "?"] = transition(data).split(" → ");
  return (
    <div className="mb-2 space-y-3 text-xs">
      {from !== null && <HealthSide label="FROM" severity={fromSeverity} reasons={from} />}
      {to !== null && <HealthSide label="TO" severity={toSeverity} reasons={to} />}
    </div>
  );
}

function ClassificationWhy({ data }: { data: Record<string, unknown> }) {
  const rule = matchedRule(data);
  if (rule === null) return null;
  return (
    <dl className="mb-2 grid grid-cols-[6rem_1fr] gap-x-3 gap-y-0.5 text-xs">
      <dt className="text-muted-foreground">Matched rule</dt>
      <dd className="break-words">{rule.name}</dd>
      {rule.on && (
        <>
          <dt className="text-muted-foreground">Matched on</dt>
          <dd className="break-words font-mono">{rule.on}</dd>
        </>
      )}
    </dl>
  );
}

/** What a row opens: the sentence (a health change: each side's worst reason), a classification's rule, the data. */
export function EventDetails({ event }: { event: AuditEvent }) {
  return (
    <div data-testid="ss-event-details">
      {event.event_type === "HEALTH_CHANGED" ? (
        <HealthWhy data={event.data} />
      ) : (
        <p className="mb-2 text-xs">{describeEvent(event)}</p>
      )}
      {event.event_type === "CLASSIFICATION_CHANGED" && <ClassificationWhy data={event.data} />}
      <pre className="whitespace-pre-wrap break-words text-xs text-muted-foreground">{JSON.stringify(visibleData(event), null, 2)}</pre>
    </div>
  );
}
