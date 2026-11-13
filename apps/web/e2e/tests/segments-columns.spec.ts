/**
 * The Segments area at full parity with segments-manager's UI (mocked;
 * ADR-0047's 3.21.0 amendment, docs/notes/2026-11-13-segments-area-api.md):
 * an Excel-style filter on every column, in the URL, and the CSV after it;
 * the Excel export of the same rows and columns. The page's other
 * behaviour: segments.spec.ts.
 */

import { readFile } from "node:fs/promises";
import { test, expect, type Page } from "@playwright/test";
import { go } from "../fixtures/api-handlers";
import { setUpSegments } from "../fixtures/segments";
import { readXlsx } from "../fixtures/xlsx";

const rows = (page: Page) => page.getByTestId("segment-row");
/** Press an export button and hand back the file the browser saved. */
async function download(page: Page, name: string) {
  const [file] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name }).click()]);
  return { name: file.suggestedFilename(), path: await file.path() };
}
const cidrs = (page: Page) => rows(page).evaluateAll((trs) => trs.map((tr) => tr.getAttribute("data-segment")));
/** A column's filter button: "Filter Type", "Filter Type (filtered: HC)". */
const filterButton = (page: Page, label: string) => page.getByRole("button", { name: new RegExp(`^Filter ${label}( \\(filtered|$)`) });
const popover = (page: Page) => page.getByTestId("column-filter");
const values = (page: Page, label: string) => popover(page).getByRole("group", { name: `${label} values` }).getByRole("checkbox");
const option = (page: Page, name: string) => popover(page).getByRole("checkbox", { name, exact: true });
/** Apply, then wait out the popover's closing animation, so the next one is the only one. */
async function apply(page: Page) {
  await popover(page).getByRole("button", { name: "Apply" }).click();
  await expect(popover(page)).toHaveCount(0);
}

test.describe("Column filters", () => {
  test("every column has one; its popover lists the column's values from the rows after search, status and site", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments?status=allocated&site=site1");
    await expect(rows(page)).toHaveCount(4);
    await expect(page.getByRole("button", { name: /^Filter / })).toHaveCount(8);

    const expected: Record<string, string[]> = {
      Type: ["HC", "INVENTORY", "UPI"],
      Site: ["site1"],
      "VLAN ID": ["1011", "1408", "1418", "1460"],
      "EPG Name": ["EPG_site1_HC_1408", "EPG_site1_HC_1418", "EPG_site1_INVENTORY_1011", "EPG_site1_UPI_1460"],
      "Network Segment": ["10.20.11.0/24", "10.20.42.0/24", "10.20.44.0/24", "10.20.60.0/24"],
      DHCP: ["Off", "On"],
      Cluster: ["ocp4-prep-eyal-site1", "ocp4-prod-herzi-site1", "ocp4-prod-mce-site1-a", "ocp4-upi-a, ocp4-upi-b"],
      Status: ["Allocated"],
    };
    for (const [label, listed] of Object.entries(expected)) {
      await filterButton(page, label).click();
      await expect(values(page, label)).toHaveText(listed);
      await expect(values(page, label).first()).toHaveAttribute("aria-checked", "true");
      await page.keyboard.press("Escape");
      await expect(popover(page)).toHaveCount(0);
    }

    // The search narrows what the popovers list, as the original's does
    await page.getByRole("searchbox", { name: "Search segments" }).fill("upi");
    await expect(rows(page)).toHaveCount(1);
    await filterButton(page, "Type").click();
    await expect(values(page, "Type")).toHaveText(["UPI"]);
  });

  test("a filter narrows the rows, marks its button, lives in the URL across a reload, and Clear removes it", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    await expect(rows(page)).toHaveCount(8);

    await filterButton(page, "Type").click();
    await expect(values(page, "Type")).toHaveText(["HC", "INVENTORY", "UPI", "(Blank)"]);
    await option(page, "(Select all)").click();
    await expect(popover(page).getByRole("button", { name: "Apply" })).toBeDisabled();
    await option(page, "UPI").click();
    await option(page, "HC").click();
    await expect(option(page, "(Select all)")).toHaveAttribute("aria-checked", "mixed");
    await apply(page);

    await expect(page).toHaveURL(/f\.type=HC&f\.type=UPI/);
    await expect.poll(() => cidrs(page)).toEqual(["10.20.42.0/24", "10.20.44.0/24", "10.20.60.0/24", "10.20.50.0/24"]);
    await expect(filterButton(page, "Type")).toHaveAttribute("data-filtered", "true");
    await expect(filterButton(page, "Site")).not.toHaveAttribute("data-filtered");
    await expect(page.getByTestId("column-filter-chip")).toHaveText("Type: HC, UPI");
    await expect(page.getByTestId("segments-summary")).toHaveText("4 of 8 segments");
    await expect(page.getByRole("group", { name: "Status" }).getByRole("button", { name: /Available/ })).toContainText("0");

    // A second column's filter narrows further; its popover lists from the rows before any column filter
    await filterButton(page, "DHCP").click();
    await expect(values(page, "DHCP")).toHaveText(["Off", "On", "(Blank)"]);
    await option(page, "On").click();
    await apply(page);
    await expect(page).toHaveURL(/f\.dhcp=Off&f\.dhcp=(&|$)/);
    await expect.poll(() => cidrs(page)).toEqual(["10.20.60.0/24"]);

    // The same URL, opened fresh, is the same view
    await page.reload();
    await expect.poll(() => cidrs(page)).toEqual(["10.20.60.0/24"]);
    await expect(filterButton(page, "Type")).toHaveAttribute("data-filtered", "true");
    await filterButton(page, "Type").click();
    await expect(option(page, "HC")).toHaveAttribute("aria-checked", "true");
    await expect(option(page, "UPI")).toHaveAttribute("aria-checked", "true");
    await expect(option(page, "INVENTORY")).toHaveAttribute("aria-checked", "false");
    await expect(option(page, "(Blank)")).toHaveAttribute("aria-checked", "false");

    // Clear drops this column's filter only
    await popover(page).getByRole("button", { name: "Clear" }).click();
    await expect(page).not.toHaveURL(/f\.type/);
    await expect.poll(() => cidrs(page)).toEqual(["10.20.60.0/24", "10.20.53.0/24"]);
    await expect(filterButton(page, "Type")).not.toHaveAttribute("data-filtered");

    // A chip removes a filter too, even with its column hidden
    await page.getByRole("button", { name: "Show or hide columns" }).click();
    await page.getByRole("checkbox", { name: "DHCP" }).click();
    await page.keyboard.press("Escape");
    await expect(filterButton(page, "DHCP")).toHaveCount(0);
    await page.getByRole("button", { name: "Remove the DHCP column filter: Off, (Blank)" }).click();
    await expect(rows(page)).toHaveCount(8);
    await expect(page).toHaveURL(/\/segments$/);
  });

  test("a popover searches its values, and select all or none acts on the values found", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    await filterButton(page, "VLAN ID").click();
    await popover(page).getByRole("searchbox", { name: "Search VLAN ID values" }).fill("14");
    await expect(values(page, "VLAN ID")).toHaveText(["1408", "1414", "1418", "1460"]);
    await option(page, "(Select all)").click();
    await expect(option(page, "(Select all)")).toHaveAttribute("aria-checked", "false");
    await apply(page);
    await expect.poll(() => cidrs(page)).toEqual(["10.20.11.0/24", "10.20.50.0/24", "10.20.52.0/24", "10.20.53.0/24"]);
    await expect(page.getByTestId("column-filter-chip")).toHaveText("VLAN ID: 4 values");

    await filterButton(page, "EPG Name").click();
    await popover(page).getByRole("searchbox", { name: "Search EPG Name values" }).fill("nothing-like-this");
    await expect(popover(page)).toContainText("No values");
    await expect(option(page, "(Select all)")).toBeDisabled();
  });

  test("the Type pill row is gone; the status tabs and the site filter stay", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    await expect(rows(page)).toHaveCount(8);
    await expect(page.getByRole("group", { name: "Type" })).toHaveCount(0);
    await expect(page.getByRole("group", { name: "Status" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Site" })).toBeVisible();
  });

  test("the CSV holds the rows the column filters keep, in the shown order", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments?f.type=HC&f.type=UPI&sort=vlan_id");
    const csv = await download(page, "CSV of 4 shown");
    expect(csv.name).toBe("segments.csv");
    const text = (await readFile(csv.path, "utf-8")).replace(/^\uFEFF/, "");
    expect(text.split("\r\n")).toEqual([
      "Type,Site,VLAN ID,EPG Name,Network Segment,DHCP,Cluster,Status",
      "HC,site1,1408,EPG_site1_HC_1408,10.20.42.0/24,On,ocp4-prep-eyal-site1,Allocated",
      "HC,site1,1418,EPG_site1_HC_1418,10.20.44.0/24,On,ocp4-prod-herzi-site1,Allocated",
      'UPI,site1,1460,EPG_site1_UPI_1460,10.20.60.0/24,Off,"ocp4-upi-a, ocp4-upi-b",Allocated',
      "HC,site2,2450,EPG_site2_HC_2450,10.20.50.0/24,On,ocp4-prep-ghost-site2,Allocated",
      "",
    ]);
  });
});

test.describe("The Excel export", () => {
  test("holds the CSV's rows and columns: what is shown, after every filter, in the shown order", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments?site=site2&f.status=Available&sort=-vlan_id");
    await page.getByRole("button", { name: "Show or hide columns" }).click();
    await page.getByRole("checkbox", { name: "Cluster" }).click();
    await page.keyboard.press("Escape");
    await expect(rows(page)).toHaveCount(2);

    const xlsx = await download(page, "Excel of 2 shown");
    expect(xlsx.name).toBe("segments.xlsx");
    const book = await readXlsx(xlsx.path);
    expect(book.sheets).toEqual(["Segments"]);
    expect(book.rows).toEqual([
      ["Type", "Site", "VLAN ID", "EPG Name", "Network Segment", "DHCP", "Status"],
      ["", "site2", 2453, "", "10.20.53.0/24", "", "Available"],
      ["", "site2", 2452, "EPG_site2_HC_2452", "10.20.52.0/24", "On", "Available"],
    ]);

    // The same rows and columns as the CSV of the same view, a VLAN ID kept as a number
    const csv = (await readFile((await download(page, "CSV of 2 shown")).path, "utf-8")).replace(/^\uFEFF/, "");
    expect(csv.split("\r\n").slice(0, -1)).toEqual(book.rows.map((row) => row.join(",")));
  });

  test("is off with nothing shown", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments?q=nothing-matches-this");
    await expect(page.getByTestId("segments-no-matches")).toBeVisible();
    await expect(page.getByRole("button", { name: "Excel of 0 shown" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "CSV of 0 shown" })).toBeDisabled();
  });
});
