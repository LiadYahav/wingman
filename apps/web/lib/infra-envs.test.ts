import { describe, expect, it } from "vitest";
import type { TemplateField } from "@/types";
import {
  addable,
  fileNodepools,
  infraEnvNames,
  isInfraEnvsPath,
  nameProblem,
  offersInfraEnvs,
  withInfraEnvs,
} from "./infra-envs";
import { placementNeeds } from "./placement";

const LARK = `# hand-written
owner:
  merkaz: "1234"
mastertag: 4.18.22-x86_64

nodepool:
- infraEnvName: dell-r660
  replicas: 3
  configs:
  - name: nm-conf-lark-dell

# Storage nodes
- infraEnvName: dell-r760
  upgradeType: Replace
  replicas: 2

vlanId: 1412

# === Added by CI ===
mcFiles:
- nm-conf-lark-dell
`;

const pools = (...fields: string[]): TemplateField[] => [
  { name: "owner_merkaz", type: "string", required: true },
  { name: "nodepools", type: "list", required: true, fields: fields.map((name) => ({ name, type: "string", required: false })) },
];

describe("the switch", () => {
  it("is day1's schema listing the input", () => {
    expect(offersInfraEnvs(pools("infra_env", "additional_infra_envs"))).toBe(true);
    expect(offersInfraEnvs(pools("infra_env"))).toBe(false);
    expect(offersInfraEnvs(undefined)).toBe(false);
  });

  it("names a nodepool's input path", () => {
    expect(isInfraEnvsPath("nodepools[2].additional_infra_envs")).toBe(true);
    expect(isInfraEnvsPath("nodepools[2].infra_env")).toBe(false);
  });
});

describe("the names", () => {
  it("are the strings of a list", () => {
    expect(infraEnvNames(["a", 1, "", "b"])).toEqual(["a", "b"]);
    expect(infraEnvNames("a")).toEqual([]);
  });

  it("offer the MCE's InfraEnvs less the nodepool's own and those listed", () => {
    expect(addable(["a", "b", "c"], "a", ["c"])).toEqual(["b"]);
  });

  it("refuse a typed name that is not an InfraEnv, is the own one, or is listed", () => {
    expect(nameProblem("ok-1", "a", [])).toBeNull();
    expect(nameProblem("Not OK", "a", [])).toMatch(/lowercase/);
    expect(nameProblem("a", "a", [])).toMatch(/own InfraEnv/);
    expect(nameProblem("b", "a", ["b"])).toBe("Already listed");
  });
});

describe("placement", () => {
  it("asks for a nodepool that draws from several InfraEnvs as one need naming them all", () => {
    const pools = [
      { infra_env: "a", replicas: 2, additional_infra_envs: ["b", "a", "Bad", "c"] },
      { infra_env: "b", replicas: "1", additional_infra_envs: [] },
    ];
    expect(placementNeeds(pools)).toEqual(["a,b,c:2", "b:1"]);
  });
});

describe("the cluster file", () => {
  it("lists its agent nodepools, Replace ones marked", () => {
    expect(fileNodepools(LARK)).toEqual([
      { index: 0, first: "dell-r660", additional: [], name: null, replace: false },
      { index: 1, first: "dell-r760", additional: [], name: null, replace: true },
    ]);
    expect(fileNodepools("platform: kubevirt\nnodepool: []\n")).toBeNull();
    expect(fileNodepools("nodepool: [\n")).toBeNull();
  });

  it("adds the list under infraEnvName and keeps every other line", () => {
    const edited = withInfraEnvs(LARK, 0, ["hp-gen11", "dell-r760"]);
    expect(edited).toBe(LARK.replace("- infraEnvName: dell-r660\n", '- infraEnvName: dell-r660\n  additionalInfraEnvNames: ["hp-gen11", "dell-r760"]\n'));
  });

  it("changes and removes a list already there, in either style", () => {
    const flow = withInfraEnvs(LARK, 1, ["a"])!;
    expect(flow).toContain('- infraEnvName: dell-r760\n  additionalInfraEnvNames: ["a"]\n  upgradeType: Replace');
    expect(withInfraEnvs(flow, 1, ["a", "b"])).toContain('additionalInfraEnvNames: ["a", "b"]\n  upgradeType');
    expect(withInfraEnvs(flow, 1, [])).toBe(LARK);
    const block = LARK.replace("  replicas: 3\n", "  additionalInfraEnvNames:\n  - a\n  - b\n  replicas: 3\n");
    expect(withInfraEnvs(block, 0, ["b"])).toBe(LARK.replace("  replicas: 3\n", '  additionalInfraEnvNames: ["b"]\n  replicas: 3\n'));
  });

  it("works on the template's own layout", () => {
    const rendered = "mastertag: 4.18.1\n\nnodepool:\n  - infraEnvName: a\n    replicas: 2\n    labels:\n      allowDeletion: false\n";
    expect(withInfraEnvs(rendered, 0, ["b"])).toBe(rendered.replace("infraEnvName: a\n", 'infraEnvName: a\n    additionalInfraEnvNames: ["b"]\n'));
  });

  it("leaves a layout it cannot edit to the person", () => {
    expect(withInfraEnvs("nodepool: [{infraEnvName: a}]\n", 0, ["b"])).toBeNull();
    expect(withInfraEnvs(LARK, 5, ["b"])).toBeNull();
    expect(withInfraEnvs("nodepool:\n- additionalInfraEnvNames: [b]\n  infraEnvName: a\n", 0, [])).toBeNull();
  });
});
