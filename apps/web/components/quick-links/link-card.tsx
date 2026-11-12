import { ArrowUpRight } from "lucide-react";
import { ArgoCdWidget } from "./argocd-widget";
import { LinkIcon } from "./link-icon";
import { StatusDot, StatusTip } from "./status-dot";
import { type StatusIndex } from "@/lib/quick-links";
import { cn } from "@/lib/utils";
import type { LinkCheck, QuickLink, QuickLinkCard } from "@/types";

/** Every link opens in a new tab, never handing Wingman's window to the page it opens. */
const NEW_TAB = { target: "_blank", rel: "noopener noreferrer" } as const;

/**
 * One card: its icon, name and description; its title opens its own link
 * (`links[0]`) in a new tab and covers the whole card. A generated card's
 * links (ArgoCD, Console) are labelled chips, each with its own dot; a file
 * card's one link has its dot in the corner. An ArgoCD with a token shows its
 * applications' counts. A link that is down or unknown says why, in words.
 */
export function LinkCard({ card, status, statusLoading }: { card: QuickLinkCard; status: StatusIndex; statusLoading: boolean }) {
  const [own] = card.links;
  const chips = card.links.length > 1 || own.label !== null;
  const trouble = card.links
    .map((link) => ({ link, check: status.check(link.ping) }))
    .filter((x): x is { link: QuickLink; check: LinkCheck } => x.check !== undefined && x.check.state !== "up");

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
        {!chips && own.ping && (
          <StatusTip
            check={status.check(own.ping)}
            trigger={<span className="relative z-10 -m-1.5 flex p-1.5" />}
          >
            <StatusDot check={status.check(own.ping)} ping={own.ping} />
          </StatusTip>
        )}
      </div>

      {card.argocd && <ArgoCdWidget reading={status.argocd(card.argocd)} loading={statusLoading} />}

      {(chips || trouble.length > 0) && (
        // Pinned to the card's foot, so a row's links line up whatever sits above them
        <div className="mt-auto space-y-2">
          {chips && (
            <div className="relative z-10 flex flex-wrap gap-1.5">
              {card.links.map((link) => (
                <LinkChip key={link.url} link={link} check={status.check(link.ping)} />
              ))}
            </div>
          )}
          {trouble.length > 0 && (
            <ul className="space-y-0.5 text-[11px] text-muted-foreground" data-testid="quick-link-trouble">
              {trouble.map(({ link, check }) => (
                <li key={link.url} className="line-clamp-2 break-words">
                  {link.label ? `${link.label}: ` : ""}
                  {describeTrouble(check)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}

/** A link that is not up, in words on the card: "Down · no answer within 3 s". */
const describeTrouble = (check: LinkCheck): string => `${check.state === "down" ? "Down" : "Unknown"} · ${check.reason}`;

function LinkChip({ link, check }: { link: QuickLink; check: LinkCheck | undefined }) {
  const label = link.label ?? link.url;
  const className = cn(
    "inline-flex items-center gap-1.5 rounded-md border bg-background px-2 py-1 text-xs font-medium",
    "transition-colors hover:border-primary/50 hover:text-primary",
    "outline-none focus-visible:ring-2 focus-visible:ring-ring"
  );
  const content = (
    <>
      {link.ping && <StatusDot check={check} ping={link.ping} />}
      {label}
      <ArrowUpRight aria-hidden className="size-3 text-muted-foreground" />
      <span className="sr-only"> (opens in a new tab)</span>
    </>
  );
  if (!link.ping) {
    return (
      <a href={link.url} {...NEW_TAB} data-testid="quick-link-chip" className={className}>
        {content}
      </a>
    );
  }
  return (
    <StatusTip check={check} trigger={<a href={link.url} {...NEW_TAB} data-testid="quick-link-chip" className={className} />}>
      {content}
    </StatusTip>
  );
}
