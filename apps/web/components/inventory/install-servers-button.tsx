"use client";

import { useId } from "react";
import { HardDriveDownload } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { Availability } from "@/types/inventory";

/**
 * The page's Install servers, for admins (a viewer gets nothing: day1 refuses
 * anyone else's start). Where installing is off here, it is shown disabled
 * with day1's one-line reason on hover and for screen readers, so the feature
 * is found and the reason is known.
 */
export function InstallServersButton({ availability, onOpen }: { availability: Availability; onOpen: () => void }) {
  const reasonId = useId();
  const off = !availability.available;
  const button = (
    <button
      type="button"
      onClick={onOpen}
      disabled={off}
      aria-describedby={off ? reasonId : undefined}
      data-testid="install-servers"
      className={buttonVariants({ size: "sm" })}
    >
      <HardDriveDownload aria-hidden className="h-4 w-4" />
      Install servers
    </button>
  );
  if (!off) return button;
  const reason = availability.detail ?? "Installing servers is off on this Wingman.";
  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger render={<span className="inline-flex" tabIndex={0} data-testid="install-servers-off" />}>
            {button}
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{reason}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <span id={reasonId} className="sr-only">{reason}</span>
    </>
  );
}
