import { describe, expect, it } from "vitest";
import { sameUser } from "./query-cache";

const alice = { username: "alice", role: "admin" };

describe("the query cache is one user's (ADR-0068)", () => {
  it("is kept for the same user in the same role", () => {
    expect(sameUser(alice, { ...alice })).toBe(true);
    expect(sameUser(null, null)).toBe(true);
  });

  it("is dropped on a sign-out, a sign-in as someone else, or a new role", () => {
    expect(sameUser(alice, null)).toBe(false);
    expect(sameUser(null, alice)).toBe(false);
    expect(sameUser(alice, { username: "vera", role: "viewer" })).toBe(false);
    expect(sameUser(alice, { username: "alice", role: "viewer" })).toBe(false);
  });
});
