import { useSyncExternalStore } from "react";

const noSubscription = () => () => {};

/**
 * False during the server render and the hydration pass, true after. The
 * signed-in user is only known in the browser (the persisted auth store), so
 * admin-only entries appear once mounted, or the server's HTML and the
 * client's first render would disagree.
 */
export function useMounted(): boolean {
  return useSyncExternalStore(noSubscription, () => true, () => false);
}
