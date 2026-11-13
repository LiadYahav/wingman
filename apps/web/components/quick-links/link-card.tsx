import { ArrowUpRight } from "lucide-react";
import { LinkIcon } from "./link-icon";
import { cn } from "@/lib/utils";
import type { QuickLink, QuickLinkCard } from "@/types";

/** Every link opens in a new tab, never handing Wingman's window to the page it opens. */
const NEW_TAB = { target: "_blank", rel: "noopener noreferrer" } as const;

/**
 * One card: its icon, name and description; its title opens its own link
 * (`links[0]`) in a new tab and covers the whole card. A generated card's
 * links (ArgoCD, Console) are labelled chips at its foot, each opening in a
 * new tab. Links only: what they point at shows its own state.
 */
export function LinkCard({ card }: { card: QuickLinkCard }) {
  const [own] = card.links;
  const chips = card.links.length > 1 || own.label !== null;

  return (
    <article
      data-testid="quick-link-card"
      data-card={card.id}
      className={cn(
        "group relative flex min-w-0 flex-col gap-3 rounded-xl border bg-card p-4 shadow-card",
        "transition-[border-color,box-shadow,translate] duration-150 ease-out",
        "hover:border-primary/40 hover:shadow-float motion-safe:hover:-translate-y-px"
      )}
    >
      <div className="flex items-start gap-3">
        <LinkIcon icon={card.icon} />
        <div className="min-w-0 flex-1">
          <h3 className="flex items-center gap-1 text-sm font-semibold leading-snug">
            <a
              href={own.url}
              {...NEW_TAB}
              data-testid="quick-link-title"
              className={cn(
                "min-w-0 truncate outline-none",
                // The stretched link: the whole card opens the card's own link
                "after:absolute after:inset-0 after:rounded-xl after:content-['']",
                "focus-visible:after:ring-2 focus-visible:after:ring-ring"
              )}
            >
              {card.name}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
            <ArrowUpRight
              aria-hidden
              className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
            />
          </h3>
          {card.description && (
            <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground" data-testid="quick-link-description">
              {card.description}
            </p>
          )}
        </div>
      </div>

      {chips && (
        // Pinned to the card's foot, so a row's links line up whatever sits above them
        <div className="relative z-10 mt-auto flex flex-wrap gap-1.5">
          {card.links.map((link) => (
            <LinkChip key={link.url} link={link} />
          ))}
        </div>
      )}
    </article>
  );
}

function LinkChip({ link }: { link: QuickLink }) {
  return (
    <a
      href={link.url}
      {...NEW_TAB}
      data-testid="quick-link-chip"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border bg-background px-2 py-1 text-xs font-medium",
        "transition-colors hover:border-primary/50 hover:text-primary",
        "outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
    >
      {link.label ?? link.url}
      <ArrowUpRight aria-hidden className="size-3 text-muted-foreground" />
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}
