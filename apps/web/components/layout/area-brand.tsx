"use client";

import Link from "next/link";
import { useCallback, useRef } from "react";
import { AreaMark } from "./area-mark";
import { triggerEasterEgg } from "./easter-egg";
import { areaById, type AreaId } from "@/lib/areas";

/** The brand fills the row beside the sidebar's toggle; in the rail it is the mark alone, centred above it. */
const BRAND_LINK = "flex h-14 min-w-0 flex-1 items-center gap-2.5 px-4 rail:h-12 rail:w-full rail:flex-none rail:justify-center rail:px-0";

const CLICKS_TO_TRIGGER = 5;
const RESET_MS = 2000;

/** Five quick clicks on an area's brand wake the easter egg: who built that area. */
function useCreditsClicks(area: AreaId) {
  const clickCount = useRef(0);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  return useCallback(() => {
    clickCount.current += 1;
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => { clickCount.current = 0; }, RESET_MS);
    if (clickCount.current >= CLICKS_TO_TRIGGER) {
      clickCount.current = 0;
      triggerEasterEgg(area);
    }
  }, [area]);
}

/** Wingman's logo and name. */
function WingmanBrand({ href }: { href: string }) {
  const onClick = useCreditsClicks("wingman");
  return (
    <Link href={href} data-testid="brand" data-area="wingman" className={BRAND_LINK} onClick={onClick}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/wingman-logo.svg" alt="Wingman" width={32} height={32} className="shrink-0 rounded-lg" />
      <span className="whitespace-nowrap text-[17px] font-semibold tracking-tight text-foreground rail:hidden">
        Wing<span className="text-primary">man</span>
      </span>
    </Link>
  );
}

/** Any other area: its own mark, or an icon on a tile the size of the logo, and its name. */
function OtherBrand({ area }: { area: Exclude<AreaId, "wingman"> }) {
  const { href, brand } = areaById(area);
  const onClick = useCreditsClicks(area);
  return (
    <Link href={href} data-testid="brand" data-area={area} className={BRAND_LINK} onClick={onClick}>
      <AreaMark mark={brand.mark} />
      <span className="truncate text-[15px] font-semibold tracking-tight text-foreground rail:sr-only">{brand.name}</span>
    </Link>
  );
}

/**
 * The top left: the platform you are in, its mark and name, linking to its
 * home. Wingman wears its logo; any other area its own mark. In the icon
 * rail, the mark alone (the name stays the link's accessible name).
 */
export function AreaBrand({ area }: { area: AreaId }) {
  if (area === "wingman") return <WingmanBrand href={areaById(area).href} />;
  return <OtherBrand area={area} />;
}
