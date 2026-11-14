import { Lock, Unplug } from "lucide-react";
import { EmptyState } from "@/components/common/empty-state";
import { isApiError } from "@/lib/api-client";

/**
 * The settings a `501` names (`details.setting`) when a page waits for one of
 * server-scan's tokens, not for server-scan: the auditor token (History,
 * Events, §14.5) or the admin token (Jobs, §15.5).
 */
type TokenSetting = "SERVER_SCAN_AUDITOR_TOKEN" | "SERVER_SCAN_ADMIN_TOKEN";

/** Whether day1's answer is a `501` waiting for `setting`: server-scan is there, that token is not. */
const needsToken = (error: unknown, setting: TokenSetting): boolean =>
  isApiError(error, "FEATURE_DISABLED") && error.details.setting === setting;

/** The audit trail's `501`: server-scan is there, its auditor token is not. */
export const needsAuditorToken = (error: unknown): boolean => needsToken(error, "SERVER_SCAN_AUDITOR_TOKEN");

/** Jobs' `501`: server-scan is there, its admin token is not. */
export const needsAdminToken = (error: unknown): boolean => needsToken(error, "SERVER_SCAN_ADMIN_TOKEN");

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
