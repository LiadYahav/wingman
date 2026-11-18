/**
 * A scroll box's height. server-scan's `useFillViewport` has no test of its
 * own (its e2e measures the page); these hold its arithmetic.
 *
 * What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
 */

import { describe, expect, it } from "vitest";
import { FILL_MIN_HEIGHT, fillHeight } from "./fill";

describe("a box that fills the page", () => {
  it("takes what is left of main under its top and above what follows it", () => {
    expect(fillHeight({ main: 900, top: 280, under: 64 })).toBe(556);
  });

  it("rounds to whole pixels", () => {
    expect(fillHeight({ main: 900.4, top: 280.2, under: 64 })).toBe(556);
  });

  it("keeps its least height in a short window, so the page scrolls a little", () => {
    expect(fillHeight({ main: 500, top: 280, under: 64 })).toBe(FILL_MIN_HEIGHT);
    expect(fillHeight({ main: 500, top: 280, under: 64 }, 160)).toBe(160);
  });
});
