"use client";

import Link from "next/link";
import { useCallback, useRef } from "react";
import { triggerEasterEgg } from "./easter-egg";
import { WINGMAN } from "@/lib/platforms";

const CLICKS_TO_TRIGGER = 5;
const RESET_MS = 2000;

/** Five quick clicks on the brand wake the easter egg: who built Wingman. */
function useCreditsClicks() {
  const clickCount = useRef(0);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  return useCallback(() => {
    clickCount.current += 1;
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => { clickCount.current = 0; }, RESET_MS);
    if (clickCount.current >= CLICKS_TO_TRIGGER) {
      clickCount.current = 0;
      triggerEasterEgg();
    }
  }, []);
}

/**
 * The top left: Wingman's logo and name, linking to its home. It fills the
 * row beside the sidebar's toggle; in the icon rail it is the logo alone,
 * centred above it (the name stays the link's accessible name).
 */
export function Brand() {
  const onClick = useCreditsClicks();
  return (
    <Link
      href={WINGMAN.href}
      data-testid="brand"
      className="flex h-14 min-w-0 flex-1 items-center gap-2.5 px-4 rail:h-12 rail:w-full rail:flex-none rail:justify-center rail:px-0"
      onClick={onClick}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/wingman-logo.svg" alt="Wingman" width={32} height={32} className="shrink-0 rounded-lg" />
      <span className="whitespace-nowrap text-[17px] font-semibold tracking-tight text-foreground rail:hidden">
        Wing<span className="text-primary">man</span>
      </span>
    </Link>
  );
}
