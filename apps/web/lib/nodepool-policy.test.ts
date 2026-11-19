import { describe, expect, it } from "vitest";
import { filePolicies, offersPolicy, policyNote, withoutDefaultPolicy, withPolicy } from "./nodepool-policy";
import type { TemplateField } from "@/types";

const FILE = `owner:
  merkaz: "1"
mastertag: 4.16.27-x86_64
nodepool:
- infraEnvName: dell-r660
  replicas: 2
  labels:
    allowDeletion: false

# storage nodes
- name: storage
  infraEnvName: dell-r760
  annotations:
    # set by the platform team
    team.io/owner: storage
    redbull.io/scale-down-policy: least-requested  # quiet nodes first
  replicas: 1
vlanId: 1412
`;

describe("the input", () => {
  it("is offered only when day1's schema lists it under nodepools", () => {
    const schema = (names: string[]): TemplateField[] => [
      { name: "nodepools", type: "list", required: true, fields: names.map((name) => ({ name, type: "string", required: false })) },
    ];
    expect(offersPolicy(schema(["infra_env", "scale_down_policy"]))).toBe(true);
    expect(offersPolicy(schema(["infra_env"]))).toBe(false);
    expect(offersPolicy(undefined)).toBe(false);
  });

  it("is left out of the request for the platform default", () => {
    expect(withoutDefaultPolicy({ infra_env: "a", scale_down_policy: "" })).toEqual({ infra_env: "a" });
    expect(withoutDefaultPolicy({ infra_env: "a", scale_down_policy: "fewest-pods" })).toEqual({ infra_env: "a", scale_down_policy: "fewest-pods" });
    const none = { infra_env: "a" };
    expect(withoutDefaultPolicy(none)).toBe(none);
  });

  it("explains each policy, the default, and an unknown one", () => {
    expect(policyNote(null)).toContain("CAPI picks");
    expect(policyNote("least-utilized")).toContain("metrics API");
    expect(policyNote("oldest-first")).toContain("refuses it");
  });
});

describe("the cluster file", () => {
  it("names each nodepool and its policy", () => {
    expect(filePolicies(FILE)).toEqual([
      { index: 0, label: "dell-r660", policy: null },
      { index: 1, label: "storage", policy: "least-requested" },
    ]);
    expect(filePolicies("nodepool: [")).toBeNull();
  });

  it("adds the block at the entry's end, as the template writes it", () => {
    expect(withPolicy(FILE, 0, "fewest-pods")).toBe(
      FILE.replace("    allowDeletion: false\n", "    allowDeletion: false\n  annotations:\n    redbull.io/scale-down-policy: fewest-pods\n")
    );
  });

  it("replaces the value and keeps its comment and the other annotations", () => {
    expect(withPolicy(FILE, 1, "fewest-pods")).toBe(FILE.replace("policy: least-requested  #", "policy: fewest-pods  #"));
  });

  it("removes the key, and the block once nothing is left in it", () => {
    const removed = withPolicy(FILE, 1, null);
    expect(removed).toBe(FILE.replace("    redbull.io/scale-down-policy: least-requested  # quiet nodes first\n", ""));
    const added = withPolicy(FILE, 0, "fewest-pods") as string;
    expect(withPolicy(added, 0, null)).toBe(FILE);
    expect(withPolicy(FILE, 0, null)).toBe(FILE);
  });

  it("adds the key beside the others in an existing block", () => {
    const without = FILE.replace("    redbull.io/scale-down-policy: least-requested  # quiet nodes first\n", "");
    expect(withPolicy(without, 1, "least-utilized")).toBe(
      without.replace("    team.io/owner: storage\n", "    team.io/owner: storage\n    redbull.io/scale-down-policy: least-utilized\n")
    );
  });

  it("leaves a layout it cannot edit to the person", () => {
    expect(withPolicy(FILE.replace("  annotations:\n    # set by the platform team\n    team.io/owner: storage\n    redbull.io/scale-down-policy: least-requested  # quiet nodes first\n", "  annotations: {team.io/owner: storage}\n"), 1, "fewest-pods")).toBeNull();
    expect(withPolicy(FILE.replace("    redbull.io/scale-down-policy:", '    "redbull.io/scale-down-policy":'), 1, "fewest-pods")).toBeNull();
    expect(withPolicy(FILE, 5, "fewest-pods")).toBeNull();
  });
});
