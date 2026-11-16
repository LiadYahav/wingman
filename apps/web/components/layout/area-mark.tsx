import { Server, type LucideIcon } from "lucide-react";
import type { BrandMark } from "@/lib/areas";

/** Every mark that is an icon: an area with no simple mark of its own. */
const ICON_MARKS: Record<Exclude<BrandMark, "wingman-logo" | "server-scan-icon">, LucideIcon> = { server: Server };

/** Wingman's logo, and server-scan's own app icon (its `frontend/public/icons/app-icon.svg`, ADR-0048). */
const IMAGE_MARKS: Record<"wingman-logo" | "server-scan-icon", string> = {
  "wingman-logo": "/wingman-logo.svg",
  "server-scan-icon": "/server-scan-icon.svg",
};

/** An area's mark, the size of Wingman's logo, decorative (the name beside it says it): its own image, or an icon on a tile. */
export function AreaMark({ mark }: { mark: BrandMark }) {
  if (mark === "wingman-logo" || mark === "server-scan-icon") {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={IMAGE_MARKS[mark]}
        alt=""
        width={32}
        height={32}
        className={mark === "wingman-logo" ? "h-8 w-8 shrink-0 rounded-lg" : "h-8 w-8 shrink-0 rounded-lg ring-1 ring-sidebar-foreground/15"}
      />
    );
  }
  const Icon = ICON_MARKS[mark];
  return (
    <span aria-hidden className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
      <Icon className="h-[18px] w-[18px]" />
    </span>
  );
}
