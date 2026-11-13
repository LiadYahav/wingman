import { describe, expect, it } from "vitest";
import { csvCell, toCsv } from "./csv";

describe("a CSV cell", () => {
  it("is left alone when plain", () => {
    expect(csvCell("EPG_site1_HC_1408")).toBe("EPG_site1_HC_1408");
    expect(csvCell("")).toBe("");
  });

  it("is quoted for a comma, a quote or a line break, quotes doubled", () => {
    expect(csvCell("ocp4-upi-a, ocp4-upi-b")).toBe('"ocp4-upi-a, ocp4-upi-b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell("two\nlines")).toBe('"two\nlines"');
  });

  it("stays text when a spreadsheet would run it as a formula", () => {
    expect(csvCell("=HYPERLINK(\"x\")")).toBe("\"'=HYPERLINK(\"\"x\"\")\"");
    expect(csvCell("+1")).toBe("'+1");
    expect(csvCell("-1")).toBe("'-1");
    expect(csvCell("@SUM(A1)")).toBe("'@SUM(A1)");
    expect(csvCell("\tx")).toBe("'\tx");
  });
});

describe("the CSV", () => {
  it("has the header, then one CRLF line per row", () => {
    expect(toCsv(["a", "b"], [["1", "2"], ["3", ""]])).toBe("a,b\r\n1,2\r\n3,\r\n");
    expect(toCsv(["a"], [])).toBe("a\r\n");
  });

});
