/**
 * Fetch now's words. The cases are server-scan's own (its
 * `RefreshButton.test.tsx` and `RowRefreshButton.test.tsx`, decision 18),
 * asked of the pure functions instead of the rendered buttons; e2e covers
 * the buttons (`server-scan-server.spec.ts`, `server-scan-servers.spec.ts`).
 *
 * What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
 */

import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api-client";
import type { Problem } from "@/types/problem";
import { FETCH_LABEL, FETCH_TITLE, fetchControl, fetchFailure, fetchedToast, rowFetchLabel } from "./refresh";

const SERVER = { id: "srv_1", name: "ocp-dell-worker-000", source_provider: "OPENMANAGE", revision: 4 };

describe("the server page's Fetch now", () => {
  it("says when nothing changed", () => {
    expect(fetchedToast(SERVER, 4)).toEqual({ title: "Fetched ocp-dell-worker-000", description: "From OPENMANAGE — no changes" });
  });

  it("says the data was updated when the revision moved", () => {
    expect(fetchedToast({ ...SERVER, revision: 5 }, 4).description).toBe("From OPENMANAGE — data updated");
  });

  it("shows the API's reason when the fetch fails", () => {
    const problem = {
      type: "/problems/server-refresh-refused",
      title: "Server Refresh Refused",
      status: 409,
      detail: "server-scan: The API is not connected to the OPENMANAGE manager; run its collector job instead.",
      code: "SERVER_REFRESH_REFUSED",
      instance: "/api/day1/server-scan/servers/srv_1/refresh",
      request_id: null,
      details: {},
    } satisfies Problem;
    expect(fetchFailure(new ApiError(409, problem, "Conflict"))).toContain("run its collector job instead");
    expect(fetchFailure(new Error("offline"))).toBe("offline");
  });

  it("is named for what it does, in server-scan's words", () => {
    expect(fetchControl(true, null, FETCH_LABEL, FETCH_TITLE)).toEqual({ label: FETCH_LABEL, title: FETCH_TITLE, off: false });
    expect(FETCH_LABEL).not.toMatch(/maintenance/i);
  });

  it("is a no-op with day1's line where it cannot work (no admin token)", () => {
    const why = "Fetch now needs server-scan's admin token: add the key admin-token to the server-scan Secret and restart day1 (SERVER_SCAN_ADMIN_TOKEN).";
    expect(fetchControl(false, why, FETCH_LABEL, FETCH_TITLE)).toEqual({ label: why, title: why, off: true });
    expect(fetchControl(false, null, FETCH_LABEL).off).toBe(true);
  });
});

describe("a row's Fetch now", () => {
  it("names the one server it fetches, and its toast its manager", () => {
    expect(rowFetchLabel("ocp-dell-worker-000")).toBe("Fetch data of ocp-dell-worker-000 now");
    expect(fetchedToast(SERVER)).toEqual({ title: "Fetched ocp-dell-worker-000", description: "From OPENMANAGE" });
    expect(fetchedToast({ ...SERVER, source_provider: null }).description).toBe("From its manager");
  });
});
