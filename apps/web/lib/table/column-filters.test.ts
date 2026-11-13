import { describe, expect, it } from "vitest";
import {
  applyColumnFilters,
  describeFilter,
  distinctValues,
  filterOptions,
  hasColumnFilters,
  readColumnFilters,
  setColumnFilter,
  sortValues,
  writeColumnFilters,
} from "./column-filters";

interface Row {
  id: string;
  type: string;
  vlan: string;
}
const ROWS: Row[] = [
  { id: "a", type: "HC", vlan: "1418" },
  { id: "b", type: "UPI", vlan: "9" },
  { id: "c", type: "", vlan: "1414" },
  { id: "d", type: "HC", vlan: "10" },
];
const text = (row: Row, column: string) => (column === "type" ? row.type : row.vlan);
const ids = (rows: Row[]) => rows.map((r) => r.id);
const COLUMNS = ["type", "vlan"] as const;

describe("a column's values", () => {
  it("are distinct, in natural order without case, the blank last", () => {
    expect(distinctValues(ROWS, (r) => r.type)).toEqual(["HC", "UPI", ""]);
    expect(distinctValues(ROWS, (r) => r.vlan)).toEqual(["9", "10", "1414", "1418"]);
    expect(sortValues(["b", "", "A", "a", "B"])).toEqual(["A", "a", "B", "b", ""]);
  });

  it("include a kept value no row has now, so it can be unchecked", () => {
    expect(filterOptions(["HC", "UPI"], ["MCE"])).toEqual(["HC", "MCE", "UPI"]);
    expect(filterOptions(["HC"], undefined)).toEqual(["HC"]);
  });
});

describe("applying the filters", () => {
  it("keeps every row without a filter", () => {
    expect(applyColumnFilters(ROWS, {}, text)).toEqual(ROWS);
  });

  it("keeps the rows whose cell is a value kept, the blank too", () => {
    expect(ids(applyColumnFilters(ROWS, { type: ["HC"] }, text))).toEqual(["a", "d"]);
    expect(ids(applyColumnFilters(ROWS, { type: ["UPI", ""] }, text))).toEqual(["b", "c"]);
  });

  it("needs every column's filter to keep a row, and matches whole values only", () => {
    expect(ids(applyColumnFilters(ROWS, { type: ["HC"], vlan: ["10", "9"] }, text))).toEqual(["d"]);
    expect(applyColumnFilters(ROWS, { vlan: ["141"] }, text)).toEqual([]);
  });
});

describe("a popover's Apply and Clear", () => {
  const options = ["HC", "UPI", ""];

  it("set the values kept, sorted", () => {
    expect(setColumnFilter({}, "type", ["UPI", "HC"], options)).toEqual({ type: ["HC", "UPI"] });
  });

  it("drop the filter when every value listed is kept, as the original does", () => {
    expect(setColumnFilter({ type: ["HC"] }, "type", ["", "UPI", "HC"], options)).toEqual({});
  });

  it("drop it on Clear, or when nothing is kept, and leave the other columns alone", () => {
    const filters = { type: ["HC"], vlan: ["9"] };
    expect(setColumnFilter(filters, "type", null, options)).toEqual({ vlan: ["9"] });
    expect(setColumnFilter(filters, "type", [], options)).toEqual({ vlan: ["9"] });
    expect(hasColumnFilters(setColumnFilter({ type: ["HC"] }, "type", null, options))).toBe(false);
  });
});

describe("the filters in the URL", () => {
  it("are one parameter per value kept, the blank an empty one", () => {
    const params = new URLSearchParams();
    writeColumnFilters(params, { vlan: ["10", "9"], type: ["", "HC"] }, COLUMNS);
    expect(params.toString()).toBe("f.type=HC&f.type=&f.vlan=9&f.vlan=10");
  });

  it("round-trip, values with commas, spaces and slashes too", () => {
    const filters = { type: ["ocp4-upi-a, ocp4-upi-b", "10.20.44.0/24", ""], vlan: ["9"] };
    const params = new URLSearchParams();
    writeColumnFilters(params, filters, COLUMNS);
    const read = readColumnFilters(new URLSearchParams(params.toString()), COLUMNS);
    expect(read).toEqual({ type: ["10.20.44.0/24", "ocp4-upi-a, ocp4-upi-b", ""], vlan: ["9"] });
  });

  it("read only the columns given, each value once", () => {
    expect(readColumnFilters(new URLSearchParams("f.type=HC&f.type=HC&f.nope=x&type=UPI"), COLUMNS)).toEqual({ type: ["HC"] });
    expect(readColumnFilters(new URLSearchParams(""), COLUMNS)).toEqual({});
  });
});

describe("a filter's chip", () => {
  it("names up to two values, else counts them", () => {
    expect(describeFilter(["HC"])).toBe("HC");
    expect(describeFilter(["HC", ""])).toBe("HC, (Blank)");
    expect(describeFilter(["HC", "UPI", "MCE"])).toBe("3 values");
  });
});
