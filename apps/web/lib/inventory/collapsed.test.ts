import { describe, expect, it } from "vitest";
import { parseCollapsed, readCollapsedMces, serializeCollapsed, toggledMce, writeCollapsedMces } from "./collapsed";

/** A Storage that keeps its values in a Map, or throws on every call. */
function storage(values = new Map<string, string>()): Pick<Storage, "getItem" | "setItem"> & { values: Map<string, string> } {
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => void values.set(key, value),
  };
}
const blocked: Pick<Storage, "getItem" | "setItem"> = {
  getItem: () => {
    throw new DOMException("denied", "SecurityError");
  },
  setItem: () => {
    throw new DOMException("full", "QuotaExceededError");
  },
};

describe("the collapsed MCEs", () => {
  it("are every card expanded unless a list of names is stored", () => {
    expect([...parseCollapsed(null)]).toEqual([]);
    expect([...parseCollapsed("")]).toEqual([]);
    expect([...parseCollapsed("not json")]).toEqual([]);
    expect([...parseCollapsed('{"a": true}')]).toEqual([]);
    expect([...parseCollapsed('["b", 3, "a"]')]).toEqual(["b", "a"]);
  });

  it("toggle one MCE and are stored in name order", () => {
    const one = toggledMce(new Set(), "ocp4-prod-mce-site1-b");
    const two = toggledMce(one, "ocp4-prod-mce-site1-a");
    expect(serializeCollapsed(two)).toBe('["ocp4-prod-mce-site1-a","ocp4-prod-mce-site1-b"]');
    expect([...toggledMce(two, "ocp4-prod-mce-site1-b")]).toEqual(["ocp4-prod-mce-site1-a"]);
  });

  it("are kept under one key and survive the next read", () => {
    const kept = storage();
    expect(writeCollapsedMces(kept, '["a"]')).toBe(true);
    expect([...kept.values.keys()]).toEqual(["wingman-inventory-collapsed"]);
    expect([...parseCollapsed(readCollapsedMces(kept))]).toEqual(["a"]);
  });

  it("with storage blocked or missing, read as nothing and say the write did not hold", () => {
    expect(readCollapsedMces(blocked)).toBeNull();
    expect(writeCollapsedMces(blocked, '["a"]')).toBe(false);
    expect(readCollapsedMces(undefined)).toBeNull();
    expect(writeCollapsedMces(undefined, '["a"]')).toBe(false);
  });
});
