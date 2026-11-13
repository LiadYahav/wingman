"use client";

import Link from "next/link";
import { useState, type ComponentProps } from "react";

/**
 * A `<Link>` for a link that repeats down a list (a row, a card): it
 * prefetches its route once someone shows intent (the pointer over it,
 * keyboard focus, a touch), never just because it is on screen.
 *
 * Next.js prefetches every `<Link>` in the viewport (`?_rsc=` requests). On a
 * list that is one request per row, and behind an HTTP/1.1 route the browser
 * opens at most six connections, so the page's own API calls queued behind
 * them (docs/ops/performance.md). Clicking navigates on the client as before;
 * `prefetch={null}` once intent shows is the guide's hover-triggered prefetch
 * (node_modules/next/dist/docs/01-app/02-guides/prefetching.md).
 */
export function IntentLink({ onMouseEnter, onFocus, onTouchStart, ...props }: Omit<ComponentProps<typeof Link>, "prefetch">) {
  const [intent, setIntent] = useState(false);
  return (
    <Link
      {...props}
      prefetch={intent ? null : false}
      onMouseEnter={(event) => {
        setIntent(true);
        onMouseEnter?.(event);
      }}
      onFocus={(event) => {
        setIntent(true);
        onFocus?.(event);
      }}
      onTouchStart={(event) => {
        setIntent(true);
        onTouchStart?.(event);
      }}
    />
  );
}
