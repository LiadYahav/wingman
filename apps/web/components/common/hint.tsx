"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * A small mark whose details wait in a tooltip, so a dense view stays quiet.
 *
 * The tooltip opens on hover, on keyboard focus and on a tap (a touch screen
 * has neither), and closes on Escape or a press elsewhere. The details are
 * also the trigger's description (`aria-describedby`, a hidden copy), so a
 * screen reader reads them without opening anything; pass `descriptionId` to
 * describe another element (a radio) with the same copy. The trigger is a
 * button at least 24px square, and a click on it goes no further (a row
 * around it is not chosen).
 */
export function Hint({
  hint,
  label,
  children,
  className,
  testId,
  descriptionId,
  descriptionTestId,
  side = "top",
}: {
  /** The details. Inline content only: it is also rendered inside a `<span>`. */
  hint: ReactNode;
  /** The trigger's name when its content is an icon. */
  label?: string;
  children: ReactNode;
  className?: string;
  testId?: string;
  descriptionId?: string;
  descriptionTestId?: string;
  side?: "top" | "bottom" | "left" | "right";
}) {
  // Base UI keeps the open state (hover and focus); a tap opens and closes it through the handle
  const [handle] = useState(() => TooltipPrimitive.createHandle());
  // The press on the trigger was a touch or a pen, not a mouse or a key
  const tapped = useRef(false);
  // Opened by a tap: the hover logic, which sees no pointer over it, must not close it
  const pinned = useRef(false);
  const ownId = useId();
  const triggerId = useId();
  const describedBy = descriptionId ?? ownId;
  return (
    // A group of its own, as the app's other tooltips: in the app-wide group, focus moving straight
    // from one mark to the next could leave the first one open and the second one shut
    <TooltipProvider>
      <Tooltip
        handle={handle}
        onOpenChange={(next, details) => {
          if (!next && pinned.current && details.reason === "trigger-hover") {
            details.cancel();
            return;
          }
          if (!next) pinned.current = false;
        }}
      >
        <TooltipTrigger
          id={triggerId}
          handle={handle}
          type="button"
          aria-label={label}
          aria-describedby={describedBy}
          data-testid={testId}
          closeOnClick={false}
          onPointerDown={(event) => {
            tapped.current = event.pointerType !== "mouse";
          }}
          onClick={(event) => {
            event.stopPropagation();
            // A mouse opened it on hover and a key on focus; a tap opens it and closes it
            if (tapped.current) {
              if (handle.isOpen) {
                pinned.current = false;
                handle.close();
              } else {
                pinned.current = true;
                handle.open(triggerId);
              }
            }
            tapped.current = false;
          }}
          className={cn(
            "inline-flex min-h-6 min-w-6 shrink-0 items-center justify-center rounded-md cursor-help",
            "outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
            className
          )}
        >
          {children}
        </TooltipTrigger>
        <TooltipContent side={side} className="block max-w-xs text-left leading-relaxed">
          {hint}
        </TooltipContent>
      </Tooltip>
      <span id={describedBy} hidden data-testid={descriptionTestId}>
        {hint}
      </span>
    </TooltipProvider>
  );
}
