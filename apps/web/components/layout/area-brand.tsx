"use client";

import Link from "next/link";
import { useCallback, useRef } from "react";
import { Server, type LucideIcon } from "lucide-react";
import { triggerEasterEgg } from "./easter-egg";
import { areaById, type AreaId, type BrandMark } from "@/lib/areas";

const CLICKS_TO_TRIGGER = 5;
const RESET_MS = 2000;

/** Wingman's logo and name; five quick clicks wake the easter egg. */
function WingmanBrand({ href }: { href: string }) {
  const clickCount = useRef(0);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleLogoClick = useCallback(() => {
    clickCount.current += 1;
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => { clickCount.current = 0; }, RESET_MS);
    if (clickCount.current >= CLICKS_TO_TRIGGER) {
      clickCount.current = 0;
      triggerEasterEgg();
    }
  }, []);

  return (
    <Link href={href} data-testid="brand" data-area="wingman" className="flex h-14 items-center gap-2.5 px-4" onClick={handleLogoClick}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/wingman-logo.svg" alt="Wingman" width={32} height={32} className="rounded-lg" />
      <span className="text-[17px] font-semibold tracking-tight text-foreground">
        Wing<span className="text-primary">man</span>
      </span>
    </Link>
  );
}

/** Every mark but Wingman's own logo, as an icon. */
const MARKS: Record<Exclude<BrandMark, "wingman-logo">, LucideIcon> = { server: Server };

/**
 * The top left: the platform you are in, its mark and name, linking to its
 * home. Wingman wears its logo; any other area its icon on a tile the size
 * of the logo.
 */
export function AreaBrand({ area }: { area: AreaId }) {
  const { href, brand } = areaById(area);
  if (brand.mark === "wingman-logo") return <WingmanBrand href={href} />;
  const Mark = MARKS[brand.mark];
  return (
    <Link href={href} data-testid="brand" data-area={area} className="flex h-14 min-w-0 items-center gap-2.5 px-4">
      <span aria-hidden className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
        <Mark className="h-[18px] w-[18px]" />
      </span>
      <span className="truncate text-[15px] font-semibold tracking-tight text-foreground">{brand.name}</span>
    </Link>
  );
}
