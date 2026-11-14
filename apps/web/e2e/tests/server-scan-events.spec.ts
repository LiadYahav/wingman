/**
 * The Server Scan area's Events page (mocked;
 * docs/notes/2026-11-13-server-scan-area-api.md §14, ADR-0048's 3.31.0
 * amendment): server-scan's audit trail of the fleet in its columns and
 * words, a server's name opening its page here, the details, the pages over
 * its cursors, the four filters in the URL under its names and sent to day1,
 * the User filter; without the auditor token, and the other states.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, json } from "../fixtures/api-handlers";
import { forbidden, off } from "../fixtures/server-scan";
import { AUDITOR_OFF, NO_EVENTS, PRUNED_ID, auditorOff, setUpEvents } from "../fixtures/server-scan-events";
import { NODE, NODE_ID } from "../fixtures/server-scan-server";

const PAGE = "/server-scan/events";
const scanNav = (page: Page) => page.getByRole("navigation", { name: "Server Scan" });
const events = (page: Page) => page.getByTestId("ss-event");
const pager = (page: Page) => page.getByTestId("ss-events-pager");
const dropdown = (page: Page, name: string) => page.getByRole("combobox", { name, exact: true });

async function choose(page: Page, name: string, option: string) {
  await dropdown(page, name).click();
  await page.getByRole("option", { name: option, exact: true }).click();
  await expect(page.getByRole("option")).toHaveCount(0);
}

test.describe("The Events page", () => {
  test("the sidebar's Events, in Activity between Fleet and Configuration, opens the trail", async ({ page }) => {
    await setUpEvents(page);
    await go(page, "/server-scan");
    await expect(scanNav(page).getByRole("link")).toHaveText(["Sites", "Servers", "Confs", "Events", "Jobs", "Rules & Policies", "Claude", "Architecture"]);
    await expect(scanNav(page)).toContainText(/Fleet.*Activity.*Configuration.*Reference/);
    await scanNav(page).getByRole("link", { name: "Events" }).click();
    await expect(page).toHaveURL(/\/server-scan\/events$/);
    await expect(scanNav(page).getByTestId("area-nav-events")).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 1, name: "Events" })).toBeVisible();
    await expect(page.getByText("The audit trail, newest first. Times are Israel time.")).toBeVisible();
    const about = page.getByTestId("ss-events-about");
    await about.hover();
    await expect(page.locator("[data-slot=tooltip-content][data-open]")).toContainText("reads API token (admin)");
  });

  test("server-scan's columns and words; a server's name opens its page here", async ({ page }) => {
    await setUpEvents(page);
    await go(page, PAGE);
    const table = page.getByRole("table", { name: "Events" });
    await expect(table.locator("thead th")).toHaveText(["Server", "What happened", "When", "User"]);
    await expect(events(page)).toHaveCount(3);
    const [job, maintenance, pruned] = [events(page).nth(0), events(page).nth(1), events(page).nth(2)];
    await expect(job.getByTestId("ss-event-server")).toHaveText("-");
    await expect(job).toContainText("JOB_TRIGGERED");
    await expect(job).toContainText("Alice Cohenuser");
    await expect(job.locator("time")).toHaveText(/^14\/11\/2026, 10:05:00/);
    await expect(maintenance).toContainText("API token (admin)token");
    await expect(pruned.getByTestId("ss-event-server")).toHaveText("Unknown server");
    await expect(pruned.getByText("Unknown server")).toHaveAttribute("title", PRUNED_ID);
    await expect(table).not.toContainText(PRUNED_ID);
    await job.getByRole("button", { name: "▸ Details" }).click();
    await expect(page.getByTestId("ss-event-details")).toContainText(
      "Ran CronJob collector-openmanage-site1 by hand as Job collector-openmanage-site1-manual-8kq2d"
    );
    await maintenance.getByRole("link", { name: NODE }).click();
    await expect(page).toHaveURL(new RegExp(`/server-scan/servers/${NODE_ID}$`));
    await expect(page.getByRole("heading", { level: 1, name: NODE })).toBeVisible();
  });

  test("Next and Previous over server-scan's cursors, Page X of Y from the first page's total", async ({ page }) => {
    const calls = await setUpEvents(page);
    await go(page, PAGE);
    await expect(pager(page)).toContainText("Page 1 of 2");
    await expect(pager(page).getByRole("button", { name: "Previous" })).toBeDisabled();
    await pager(page).getByRole("button", { name: "Next" }).click();
    await expect(events(page)).toHaveCount(2);
    await expect(events(page).nth(1)).toContainText("SERVER_CREATED");
    await expect(pager(page)).toContainText("Page 2 of 2");
    await expect(pager(page).getByRole("button", { name: "Next" })).toBeDisabled();
    await pager(page).getByRole("button", { name: "Previous" }).click();
    await expect(events(page)).toHaveCount(3);
    expect(calls.lists).toEqual([{}, { cursor: "c2" }]);
  });

  test("the filters are in the URL under server-scan's names, and day1 is asked with them", async ({ page }) => {
    const calls = await setUpEvents(page);
    await go(page, `${PAGE}?event_type=HEALTH_STATUS_CHANGED&server_name=ocp-dell&range=custom&from=01/10/2026 09:00&to=02/10/2026`);
    await expect(events(page)).toHaveCount(3);
    expect(calls.lists[0]).toEqual({
      event_type: "HEALTH_CHANGED",
      server_name: "ocp-dell",
      since: "2026-10-01T06:00:00.000Z",
      until: "2026-10-01T21:00:00.000Z",
    });
    await expect(page.getByTestId("ss-events-filters").locator("label")).toHaveText([
      "Event type", "Server", "User", "Time range", "From (Israel time)", "To (exclusive) (Israel time)",
    ]);
    await expect(dropdown(page, "Event type")).toContainText("HEALTH_CHANGED");
    await expect(dropdown(page, "Time range")).toContainText("Custom");

    await choose(page, "Event type", "SERVER_PRUNED");
    await expect(page).toHaveURL(/event_type=SERVER_PRUNED/);
    await expect.poll(() => calls.lists.at(-1)?.event_type).toBe("SERVER_PRUNED");

    await page.getByLabel("To (exclusive) (Israel time)").fill("31/02/2026");
    await expect(page.getByText("Use DD/MM/YYYY HH:MM")).toBeVisible();
    await expect.poll(() => calls.lists.at(-1)).toEqual({ event_type: "SERVER_PRUNED", server_name: "ocp-dell", since: "2026-10-01T06:00:00.000Z" });

    await page.getByLabel("Server", { exact: true }).fill("csfake");
    await expect(page).toHaveURL(/server_name=csfake/);
    await expect.poll(() => calls.lists.at(-1)?.server_name).toBe("csfake");

    await choose(page, "Time range", "Last 24 hours");
    await expect(page.getByLabel("From (Israel time)")).toHaveCount(0);
    await expect.poll(() => {
      const last = calls.lists.at(-1) ?? {};
      return [Boolean(last.since), "until" in last];
    }).toEqual([true, false]);
    await choose(page, "Event type", "All");
    await expect(page).not.toHaveURL(/event_type=/);
  });

  test("the User filter: All, then each actor with its count; one picked by its id, All clears", async ({ page }) => {
    const calls = await setUpEvents(page);
    await go(page, PAGE);
    const user = dropdown(page, "User");
    await expect(user).toContainText("All");
    await user.click();
    await expect(page.getByRole("option")).toHaveText(["All", "System (ingestion)9 events", "Alice Cohen3 events", "API token (admin)2 events"]);
    await page.getByRole("combobox", { name: "Name or id" }).fill("api-token");
    await expect(page.getByRole("option")).toHaveText(["API token (admin)2 events"]);
    await page.getByRole("combobox", { name: "Name or id" }).fill("nobody");
    await expect(page.getByText("No matching user")).toBeVisible();
    await page.getByRole("combobox", { name: "Name or id" }).fill("alice");
    await page.getByRole("option", { name: /Alice Cohen/ }).click();
    await expect(page).toHaveURL(/actor_id=alice/);
    await expect(user).toContainText("Alice Cohen");
    await expect.poll(() => calls.lists.at(-1)?.actor_id).toBe("alice");
    await choose(page, "User", "All");
    await expect(page).not.toHaveURL(/actor_id=/);
    await expect(user).toContainText("All");
    // The unfiltered list was read under 30 seconds ago: shown again, not asked again
    await expect(events(page)).toHaveCount(3);
    expect(calls.lists).toEqual([{}, { actor_id: "alice" }]);
  });

  test("without server-scan's auditor token it says so in one line, with no filters", async ({ page }) => {
    await setUpEvents(page, { events: auditorOff, actors: auditorOff });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-events-off")).toHaveText(AUDITOR_OFF);
    await expect(page.getByTestId("ss-events-filters")).toHaveCount(0);
    await expect(page.getByTestId("ss-off")).toHaveCount(0);
  });

  test("an empty trail, server-scan failing, a viewer and an unset area are each told so", async ({ page }) => {
    await setUpEvents(page, { events: (route) => json(route, NO_EVENTS) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-events-empty")).toHaveText("No events recorded.");
    await page.unrouteAll({ behavior: "ignoreErrors" });

    const refused = "server-scan refused Wingman's auditor token (403) listing events: check SERVER_SCAN_AUDITOR_TOKEN";
    await setUpEvents(page, { events: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", refused) });
    await go(page, PAGE);
    await expect(page.getByRole("alert").filter({ hasText: refused })).toContainText("The events could not be read from server-scan");
    await page.unrouteAll({ behavior: "ignoreErrors" });

    await setUpEvents(page, { events: forbidden, actors: forbidden });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-forbidden")).toContainText("For admins");
    await page.unrouteAll({ behavior: "ignoreErrors" });

    await setUpEvents(page, { events: off, actors: off });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-off")).toContainText("Server Scan is not set up");
  });
});
