import { describe, expect, it } from "vitest";
import { offeredRelease, withoutArch } from "./release-tags";

describe("the release a tag names", () => {
  it.each(["x86_64", "aarch64", "ppc64le", "s390x", "multi"])("drops the %s architecture", (arch) => {
    expect(withoutArch(`4.16.27-${arch}`)).toBe("4.16.27");
  });

  it("keeps a prerelease, and only the last part is an architecture", () => {
    expect(withoutArch("4.16.0-rc.1-x86_64")).toBe("4.16.0-rc.1");
    expect(withoutArch("4.16.0-ec.2-aarch64")).toBe("4.16.0-ec.2");
    expect(withoutArch("4.16.0-rc.1")).toBe("4.16.0-rc.1");
    expect(withoutArch("4.16.27-x86_64-x86_64")).toBe("4.16.27-x86_64");
  });

  it("leaves a tag without an architecture as it is", () => {
    expect(withoutArch("4.16.27")).toBe("4.16.27");
    expect(withoutArch("")).toBe("");
    expect(withoutArch("x86_64")).toBe("x86_64");
  });

  it("leaves a suffix that is no architecture, upper case included", () => {
    expect(withoutArch("4.19.10-multi-arch")).toBe("4.19.10-multi-arch");
    expect(withoutArch("4.16.27-X86_64")).toBe("4.16.27-X86_64");
    expect(withoutArch("4.16.27-arm64")).toBe("4.16.27-arm64");
    expect(withoutArch("4.16.27-")).toBe("4.16.27-");
  });
});

describe("the offered release a version names", () => {
  const OFFERED = ["4.18.56", "4.17.58", "4.16.0-rc.1"];

  it("finds a release with or without its architecture, as typed", () => {
    expect(offeredRelease("4.18.56", OFFERED)).toBe("4.18.56");
    expect(offeredRelease("4.18.56-x86_64", OFFERED)).toBe("4.18.56");
    expect(offeredRelease(" 4.17.58-aarch64 ", OFFERED)).toBe("4.17.58");
    expect(offeredRelease("4.16.0-rc.1-x86_64", OFFERED)).toBe("4.16.0-rc.1");
  });

  it("is null for a release not offered, an empty value or no string at all", () => {
    expect(offeredRelease("4.19.10-x86_64", OFFERED)).toBeNull();
    expect(offeredRelease("4.16.0-x86_64", OFFERED)).toBeNull();
    expect(offeredRelease("4.18.56-arm64", OFFERED)).toBeNull();
    expect(offeredRelease("", OFFERED)).toBeNull();
    expect(offeredRelease("  ", [...OFFERED, ""])).toBeNull();
    expect(offeredRelease("-x86_64", [...OFFERED, ""])).toBeNull();
    expect(offeredRelease(undefined, OFFERED)).toBeNull();
    expect(offeredRelease(4.18, OFFERED)).toBeNull();
  });
});
