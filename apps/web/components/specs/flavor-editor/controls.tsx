"use client";

import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { AlertCircle, AlertTriangle, Lock } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

/**
 * A segmented control: one choice of a few, every choice visible. It is a
 * radio group (arrow keys move the choice, Tab leaves it), so its state is
 * read the same way by a screen reader and a test.
 */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "sm",
  tone = () => "neutral",
  className,
  testId,
}: {
  options: readonly SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** The group's accessible name. */
  label: string;
  size?: "xs" | "sm";
  /** A chosen segment's colour: `accent` marks a choice that constrains (Locked), `warning` one that does not hold. */
  tone?: (value: T) => "neutral" | "accent" | "warning";
  className?: string;
  testId?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (event: KeyboardEvent, index: number) => {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (index + step + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div
      role="radiogroup"
      aria-label={label}
      data-testid={testId}
      className={cn("inline-flex shrink-0 items-center gap-0.5 rounded-lg bg-muted p-0.5", className)}
    >
      {options.map((option, index) => {
        const selected = option.value === value;
        const chosenTone = selected ? tone(option.value) : "neutral";
        return (
          <button
            key={option.value}
            ref={(el) => {
              refs.current[index] = el;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(e) => move(e, index)}
            className={cn(
              "inline-flex items-center gap-1 rounded-md font-medium whitespace-nowrap outline-none transition-[background-color,color,box-shadow] duration-150 focus-visible:ring-2 focus-visible:ring-ring/60",
              size === "xs" ? "h-6 px-2 text-[11px]" : "h-7 px-2.5 text-xs",
              !selected
                ? "text-muted-foreground hover:text-foreground"
                : chosenTone === "accent"
                  ? "bg-primary/15 text-primary shadow-sm ring-1 ring-inset ring-primary/25"
                  : chosenTone === "warning"
                    ? "bg-status-warning/15 text-status-warning-fg shadow-sm ring-1 ring-inset ring-status-warning/30"
                    : "bg-background text-foreground shadow-sm dark:bg-input/40"
            )}
          >
            {option.icon}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

const LOCK_OPTIONS = [
  { value: "preset", label: "Preset" },
  { value: "locked", label: "Locked", icon: <Lock className="h-3 w-3" aria-hidden /> },
] as const satisfies readonly SegmentOption<"preset" | "locked">[];

/**
 * Preset (prefilled, a cluster may change it) or Locked (every cluster gets
 * exactly this value). `notEnforced`: the saved lock breaks a rule, so a
 * create does not enforce it (it is not in the flavor's `enforced_locks`).
 */
function LockControl({
  locked,
  onChange,
  label,
  notEnforced = false,
}: {
  locked: boolean;
  onChange: (locked: boolean) => void;
  /** What the value is, e.g. "Owner merkaz"; the group is named "<label>: preset or locked". */
  label: string;
  notEnforced?: boolean;
}) {
  return (
    <Segmented
      options={LOCK_OPTIONS}
      value={locked ? "locked" : "preset"}
      onChange={(v) => onChange(v === "locked")}
      label={`${label}: preset or locked`}
      size="xs"
      tone={(v) => (v === "locked" ? (notEnforced ? "warning" : "accent") : "neutral")}
    />
  );
}

/** What a value's lock state means for a cluster, in one line. */
function lockHint(locked: boolean, empty: boolean): string {
  if (locked) return "Fixed: every cluster gets exactly this value.";
  if (empty) return "Not set: each cluster fills it in.";
  return "Prefilled: a cluster may change it.";
}

export const fieldId = (path: string) => `field-${path.replace(/[^A-Za-z0-9]+/g, "-")}`;

/**
 * One value of the flavor: its label, the Preset/Locked control when it can
 * be locked, the input, and below it what the choice means or what is wrong.
 * Problems are day1's or the editor's own; `warn` ones do not block a save.
 */
export function ValueField({
  path,
  label,
  locked,
  onLockedChange,
  empty,
  problems = [],
  hint,
  children,
  className,
  labelsInput = true,
  notEnforced,
}: {
  path: string;
  label: string;
  /** Omitted for a value that cannot be locked (a preset only). */
  locked?: boolean;
  onLockedChange?: (locked: boolean) => void;
  empty: boolean;
  problems?: string[];
  /** Replaces the lock hint. */
  hint?: ReactNode;
  children: (ids: { inputId: string; describedBy: string; invalid: boolean }) => ReactNode;
  className?: string;
  /** `false` when the control names itself (a radio group, a list): the label is then a heading. */
  labelsInput?: boolean;
  /** Why the saved lock is not enforced (day1's warning), shown while the draft still locks it. */
  notEnforced?: string;
}) {
  const inputId = useId();
  const hintId = useId();
  const lockable = locked !== undefined && onLockedChange !== undefined;
  const invalid = problems.length > 0;
  return (
    <div id={fieldId(path)} className={cn("min-w-0 scroll-mt-28 space-y-1.5", className)} data-field={path}>
      <div className="flex min-h-7 items-center justify-between gap-2">
        {labelsInput ? (
          <label htmlFor={inputId} className="truncate text-[13px] font-medium text-foreground/90">
            {label}
          </label>
        ) : (
          <span className="truncate text-[13px] font-medium text-foreground/90">{label}</span>
        )}
        {lockable && (
          <LockControl locked={locked} onChange={onLockedChange} label={label} notEnforced={Boolean(locked && notEnforced)} />
        )}
      </div>
      {children({ inputId, describedBy: hintId, invalid })}
      <div id={hintId} className="space-y-0.5 text-xs">
        {locked && notEnforced && <NotEnforced reason={notEnforced} />}
        {invalid ? (
          <ul className="space-y-0.5 text-destructive" role="alert">
            {problems.map((p) => (
              <li key={p} className="flex items-start gap-1.5">
                <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                <span className="break-words">{p}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={cn("text-muted-foreground", locked && !notEnforced && "text-primary/90")}>
            {hint ?? (lockable ? lockHint(Boolean(locked), empty) : empty ? "Not set: each cluster fills it in." : "Prefilled: a cluster may change it.")}
          </p>
        )}
      </div>
    </div>
  );
}

/** A saved lock a create does not enforce, and why; a save refuses it until it is fixed. */
export function NotEnforced({ reason }: { reason: string }) {
  return (
    <p className="flex items-start gap-1.5 text-status-warning-fg" data-testid="lock-not-enforced">
      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
      <span className="break-words">
        <span className="font-medium">Locked, but not enforced:</span> {reason}. A save refuses it until it is fixed.
      </span>
    </p>
  );
}

export const inputCls =
  "h-9 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-sm transition-[border-color,box-shadow] outline-none placeholder:text-muted-foreground/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 aria-invalid:border-destructive/70 aria-invalid:ring-destructive/20 dark:bg-input/30";

/** A section's title row: the step number, the title, and one line about it. */
export function SectionHeader({ step, title, description, id }: { step: number; title: string; description: string; id: string }) {
  return (
    <header className="flex items-start gap-3">
      <span
        aria-hidden
        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold tabular-nums text-muted-foreground"
      >
        {step}
      </span>
      <div className="min-w-0">
        <h2 id={id} className="text-lg font-semibold leading-tight tracking-[-0.01em]">
          {title}
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
      </div>
    </header>
  );
}

/** A group of fields inside a section, under a small heading. */
export function FieldGroup({ title, description, children, aside }: { title: string; description?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">{title}</h3>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
        </div>
        {aside}
      </div>
      {children}
    </div>
  );
}
