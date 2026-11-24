/**
 * The look Inventory Management's two tables share, the pools and the runs:
 * dense rows under a sticky, translucent header.
 *
 * The lines between rows, and the firmer one under the header, come from the
 * foreground so they show in both themes (1.4-1.5:1 and 1.5-1.8:1, about
 * Apple's separators; the theme's `border` at 60% was 1.15:1), and 3:1 or
 * more when the system asks for more contrast.
 */
export const DIVIDER = {
  rows: "divide-foreground/15 contrast-more:divide-foreground/50",
  header: "border-foreground/20 contrast-more:border-foreground/55",
};

/** The header row's background: it stays in view over the rows scrolling under it. */
export const STICKY_HEAD = "sticky top-0 z-10 bg-muted/90 backdrop-blur supports-[backdrop-filter]:bg-muted/75";

export const HEADER_CELL = "whitespace-nowrap px-3 py-2 text-left text-xs font-semibold tracking-[0.01em] text-foreground/75";
