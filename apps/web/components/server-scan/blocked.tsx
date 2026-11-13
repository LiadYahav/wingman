import { Lock, Unplug } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { isApiError } from "@/lib/api-client";

/** Whether day1's answer means the area cannot be shown at all: not an admin (403), or server-scan not configured (501). */
export const isBlocked = (error: unknown): boolean => isApiError(error, "FORBIDDEN") || isApiError(error, "FEATURE_DISABLED");

/** Why a Server Scan page cannot show anything: not an admin, or server-scan not configured. */
export function Blocked({ error }: { error: unknown }) {
  if (isApiError(error, "FORBIDDEN")) {
    return (
      <EmptyState
        icon={Lock}
        bordered
        title="For admins"
        description="Server Scan is for Wingman's admins for now, until Wingman has finer roles."
        data-testid="ss-forbidden"
      />
    );
  }
  return (
    <EmptyState
      icon={Unplug}
      bordered
      title="Server Scan is not set up"
      description="Wingman shows server-scan's pages once day1 knows where it is: set serverScan.url in the chart (SERVER_SCAN_URL)."
      data-testid="ss-off"
    />
  );
}
