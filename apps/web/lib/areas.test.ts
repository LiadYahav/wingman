import { describe, expect, it } from "vitest";
import { areaOf, areasFor } from "./areas";

describe("the areas", () => {
  it("puts /segments and below in Segments, everything else in Wingman", () => {
    expect(areaOf("/segments")).toBe("segments");
    expect(areaOf("/segments/site1")).toBe("segments");
    expect(areaOf("/")).toBe("wingman");
    expect(areaOf("/clusters/ocp4-prod-herzi-site1")).toBe("wingman");
    expect(areaOf("/segments-old")).toBe("wingman");
  });

  it("lists Segments only for someone who has it", () => {
    expect(areasFor({ segments: true }).map((a) => [a.label, a.href])).toEqual([
      ["Wingman", "/"],
      ["Segments", "/segments"],
    ]);
    expect(areasFor({ segments: false }).map((a) => a.id)).toEqual(["wingman"]);
  });
});
