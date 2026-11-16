"use client";

import { Minus, Plus } from "lucide-react";
import { MAX_REPLICAS, stepped, typedReplicas, type ScaleMode } from "@/lib/scale-model";
import { cn } from "@/lib/utils";

/** The id of a stepper's field, for focus to go back to once its change is cancelled. */
export const stepperInputId = ({ mode, target }: { mode: ScaleMode; target: string }) => `scale-input-${mode}-${target}`;

/**
 * Quiet until wanted: in a card or a row (`group/pool`) the frame and the
 * − + show faintly, and fully on hover, on focus and on a touch screen. The
 * number always reads at full strength.
 */
const QUIET_FRAME = cn(
  "border-transparent bg-transparent shadow-none dark:bg-transparent",
  "group-hover/pool:border-border group-hover/pool:bg-background group-hover/pool:shadow-xs dark:group-hover/pool:bg-input/30",
  "focus-within:border-border focus-within:bg-background dark:focus-within:bg-input/30",
  "pointer-coarse:border-border pointer-coarse:bg-background dark:pointer-coarse:bg-input/30"
);
const QUIET_ICON = "opacity-50 group-hover/pool:opacity-100 group-focus-within/stepper:opacity-100 pointer-coarse:opacity-100";
const QUIET_FIELD = "border-transparent group-hover/pool:border-border group-focus-within/stepper:border-border pointer-coarse:border-border";

/** The − and + of a stepper: the press shows at once, on the button and its icon. */
const stepClass = cn(
  "group/step flex size-8 shrink-0 items-center justify-center text-muted-foreground outline-none pointer-coarse:size-10",
  "transition-colors duration-150 hover:bg-muted hover:text-foreground active:bg-muted-foreground/15 active:duration-0",
  "focus-visible:bg-muted focus-visible:text-foreground focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
  "disabled:pointer-events-none disabled:opacity-35"
);
const iconClass =
  "size-4 transition-[transform,opacity] duration-100 ease-out group-active/step:scale-[0.82] motion-reduce:transition-none motion-reduce:group-active/step:scale-100";

/**
 * − [n] +: one NodePool's replicas or a hardware type's total. Each button
 * moves it by one, the arrow keys too, and it can be typed. `changed` marks
 * the one stepper whose number differs from now.
 */
export function ReplicasStepper({
  name,
  value,
  onValue,
  disabled,
  changed,
  describedBy,
  inputId,
  quiet = false,
}: {
  /** The NodePool or the hardware type: it names the group and its buttons. */
  name: string;
  /** `NaN` while the field is empty. */
  value: number;
  onValue: (replicas: number) => void;
  disabled: boolean;
  changed: boolean;
  describedBy?: string;
  /** For focus to come back to after a change is cancelled. */
  inputId?: string;
  quiet?: boolean;
}) {
  const shown = Number.isNaN(value) ? 0 : value;
  const hushed = quiet && !changed;
  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    onValue(stepped(value, e.key === "ArrowUp" ? 1 : -1));
  };
  return (
    <div
      role="group"
      aria-label={`${name} replicas`}
      aria-describedby={describedBy}
      data-testid="scale-stepper"
      data-changed={changed}
      className={cn(
        "group/stepper inline-flex shrink-0 items-stretch overflow-hidden rounded-lg border bg-background shadow-xs dark:bg-input/30",
        "transition-[border-color,box-shadow,background-color] duration-150",
        hushed && QUIET_FRAME,
        changed && "border-primary/70 ring-3 ring-primary/15",
        disabled && "shadow-none"
      )}
    >
      <button
        type="button"
        onClick={() => onValue(stepped(value, -1))}
        disabled={disabled || shown <= 0}
        aria-label={`One replica fewer for ${name}`}
        data-testid="scale-minus"
        className={stepClass}
      >
        <Minus className={cn(iconClass, hushed && QUIET_ICON)} aria-hidden />
      </button>
      <input
        id={inputId}
        type="text"
        inputMode="numeric"
        role="spinbutton"
        aria-label={`Replicas of ${name}`}
        aria-valuemin={0}
        aria-valuemax={MAX_REPLICAS}
        aria-valuenow={Number.isNaN(value) ? undefined : value}
        aria-invalid={Number.isNaN(value) || value > MAX_REPLICAS || undefined}
        autoComplete="off"
        value={Number.isNaN(value) ? "" : String(value)}
        onChange={(e) => onValue(typedReplicas(e.target.value))}
        onKeyDown={onKeyDown}
        onFocus={(e) => e.currentTarget.select()}
        disabled={disabled}
        data-testid="scale-replicas"
        className={cn(
          "w-11 min-w-0 border-x bg-transparent text-center text-sm font-semibold tabular-nums outline-none",
          "focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:text-muted-foreground",
          hushed && QUIET_FIELD,
          changed && "text-primary"
        )}
      />
      <button
        type="button"
        onClick={() => onValue(stepped(value, 1))}
        disabled={disabled || shown >= MAX_REPLICAS}
        aria-label={`One replica more for ${name}`}
        data-testid="scale-plus"
        className={stepClass}
      >
        <Plus className={cn(iconClass, hushed && QUIET_ICON)} aria-hidden />
      </button>
    </div>
  );
}
