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

/** Every mark that is an icon: an area with no simple mark of its own. */
const ICON_MARKS: Record<Exclude<BrandMark, "wingman-logo" | "server-scan-icon">, LucideIcon> = { server: Server };

/** server-scan's own app icon (its `frontend/public/icons/app-icon.svg`, ADR-0048). */
const IMAGE_MARKS: Record<"server-scan-icon", string> = { "server-scan-icon": "/server-scan-icon.svg" };

/** An area's mark, the size of Wingman's logo: its own image, or an icon on a tile. */
function Mark({ mark }: { mark: Exclude<BrandMark, "wingman-logo"> }) {
  if (mark === "server-scan-icon") {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={IMAGE_MARKS[mark]} alt="" width={32} height={32} className="h-8 w-8 shrink-0 rounded-lg ring-1 ring-sidebar-foreground/15" />;
  }
  const Icon = ICON_MARKS[mark];
  return (
    <span aria-hidden className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
      <Icon className="h-[18px] w-[18px]" />
    </span>
  );
}

/**
 * The top left: the platform you are in, its mark and name, linking to its
 * home. Wingman wears its logo; any other area its own mark, or an icon on a
 * tile the size of the logo.
 */
export function AreaBrand({ area }: { area: AreaId }) {
  const { href, brand } = areaById(area);
  if (brand.mark === "wingman-logo") return <WingmanBrand href={href} />;
  return (
    <Link href={href} data-testid="brand" data-area={area} className="flex h-14 min-w-0 items-center gap-2.5 px-4">
      <Mark mark={brand.mark} />
      <span className="truncate text-[15px] font-semibold tracking-tight text-foreground">{brand.name}</span>
    </Link>
  );
}
