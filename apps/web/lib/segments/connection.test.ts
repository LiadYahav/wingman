import { describe, expect, it } from "vitest";
import { connection, offlineLabel, onlineLabel } from "./connection";

describe("the connection state", () => {
  it("is online after a good read, and with no attempt yet", () => {
    expect(connection([{ at: 10, failure: null }])).toEqual({ state: "online", label: onlineLabel });
    expect(connection([])).toEqual({ state: "online", label: onlineLabel });
  });

  it("is offline when the latest attempt failed, with its reason", () => {
    expect(connection([{ at: 10, failure: null }, { at: 40, failure: "segments-manager answered 503" }])).toEqual({
      state: "offline",
      label: "segments-manager didn't answer the last refresh: segments-manager answered 503; showing the last good data",
    });
  });

  it("is online again once a later attempt succeeds, whichever came first in the list", () => {
    expect(connection([{ at: 70, failure: null }, { at: 40, failure: "timed out" }]).state).toBe("online");
    expect(connection([{ at: 40, failure: "timed out" }, { at: 70, failure: null }]).state).toBe("online");
  });

  it("takes the failure when a failure and a success end at the same moment", () => {
    expect(connection([{ at: 40, failure: null }, { at: 40, failure: "x" }])).toEqual({ state: "offline", label: offlineLabel("x") });
  });
});
