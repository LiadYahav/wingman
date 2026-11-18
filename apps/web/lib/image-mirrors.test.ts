import { describe, expect, it } from "vitest";
import {
  DROP_MCE_MIRRORS,
  IMAGE_MIRRORS,
  asMirrorEntries,
  isMirrorInput,
  mirrorEntryProblems,
  mirrorIssues,
  mirrorListText,
  mirrorValueText,
  noMirrorsProblem,
  readableMirrorProblem,
} from "./image-mirrors";

const OPERATORS = { source: "registry.example.com/team/operators", mirrors: ["mirror.example.com/team/operators"] };
const RELEASE = { source: "registry.example.com/ocp/release", mirrors: ["mirror.example.com/ocp/release", "mirror2.example.com/ocp/release"] };

describe("image mirrors as values", () => {
  it("knows the two inputs by name", () => {
    expect(isMirrorInput(IMAGE_MIRRORS)).toBe(true);
    expect(isMirrorInput(DROP_MCE_MIRRORS)).toBe(true);
    expect(isMirrorInput("platform")).toBe(false);
  });

  it("reads entries, keeping the ones being typed and dropping what is not one", () => {
    expect(asMirrorEntries([OPERATORS, { source: "", mirrors: [""] }, "x", { mirrors: [1, "m"] }])).toEqual([
      OPERATORS,
      { source: "", mirrors: [""] },
      { source: "", mirrors: ["m"] },
    ]);
    expect(asMirrorEntries(undefined)).toEqual([]);
  });

  it("reads a list as source → mirrors, and nothing else", () => {
    expect(mirrorListText([OPERATORS, RELEASE])).toBe(
      "registry.example.com/team/operators → mirror.example.com/team/operators; registry.example.com/ocp/release → mirror.example.com/ocp/release, mirror2.example.com/ocp/release"
    );
    expect(mirrorListText([{ name: "nm-conf" }])).toBeNull();
    expect(mirrorListText([])).toBeNull();
  });

  it("says whether the MCE's default mirrors are kept; only a JSON true drops them", () => {
    expect(mirrorValueText(DROP_MCE_MIRRORS, true)).toMatch(/^Dropped/);
    expect(mirrorValueText(DROP_MCE_MIRRORS, false)).toMatch(/^Kept/);
    expect(mirrorValueText(DROP_MCE_MIRRORS, "true")).toMatch(/^Kept/);
    expect(mirrorValueText(IMAGE_MIRRORS, [])).toBe("None of its own");
  });
});

describe("day1's rules, mirrored", () => {
  it("accepts entries with a source and its mirrors", () => {
    expect(mirrorEntryProblems([OPERATORS, RELEASE])).toEqual([]);
    expect(mirrorIssues({ [IMAGE_MIRRORS]: [OPERATORS], [DROP_MCE_MIRRORS]: true })).toEqual([]);
  });

  it("needs a source, a mirror, no spaces, quotes or repeats", () => {
    const problems = mirrorEntryProblems([
      { source: "", mirrors: [] },
      { source: "registry.example.com/a b", mirrors: ['mirror.example.com/"a"'] },
      { source: OPERATORS.source, mirrors: ["m.example.com", "m.example.com"] },
      { source: OPERATORS.source, mirrors: ["n.example.com"] },
    ]);
    expect(problems).toEqual([
      { entry: 0, message: "Give the source" },
      { entry: 0, message: "Give at least one mirror" },
      { entry: 1, message: "The source has a space in it" },
      { entry: 1, mirror: 0, message: "The mirror may not hold a quote, a backslash or a control character" },
      { entry: 2, mirror: 1, message: "m.example.com is listed twice" },
      {
        entry: 3,
        message: `${OPERATORS.source} is listed twice (entry 3): give all its mirrors in one entry`,
      },
    ]);
  });

  it("refuses dropping the MCE's mirrors when the cluster has none of its own", () => {
    expect(noMirrorsProblem({ [DROP_MCE_MIRRORS]: true })).toBe(
      "The cluster would have no image mirrors: add its own, or keep the MCE's default mirrors"
    );
    expect(noMirrorsProblem({ [DROP_MCE_MIRRORS]: true, [IMAGE_MIRRORS]: [] })).not.toBeNull();
    expect(noMirrorsProblem({ [DROP_MCE_MIRRORS]: false })).toBeNull();
    expect(mirrorIssues({ [DROP_MCE_MIRRORS]: true }).map((i) => i.path)).toEqual([DROP_MCE_MIRRORS]);
  });

  it("puts each entry's problems at the list, and a non-boolean switch at the switch", () => {
    expect(mirrorIssues({ [IMAGE_MIRRORS]: [{ source: "", mirrors: ["m.example.com"] }], [DROP_MCE_MIRRORS]: "true" })).toEqual([
      { path: IMAGE_MIRRORS, message: "Entry 1: Give the source" },
      { path: DROP_MCE_MIRRORS, message: "On or off (true or false)" },
    ]);
    expect(mirrorIssues({ [IMAGE_MIRRORS]: "registry.example.com" })[0]).toEqual({ path: IMAGE_MIRRORS, message: "A list of mirror entries" });
  });

  it("words day1's problems under the list by entry and mirror", () => {
    expect(readableMirrorProblem("[1].source: must not be empty")).toBe("Entry 2, source: must not be empty");
    expect(readableMirrorProblem("[0].mirrors[2]: is listed twice")).toBe("Entry 1, mirror 3: is listed twice");
    expect(readableMirrorProblem("[0].mirrors: needs at least one mirror")).toBe("Entry 1, mirrors: needs at least one mirror");
    expect(readableMirrorProblem("the template does not read it")).toBe("the template does not read it");
  });
});
