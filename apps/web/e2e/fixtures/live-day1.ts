/**
 * The day1 live specs' steps (live-day1-flows, live-flavors): sign in through
 * the dev login, call the API as that person, and merge an MR as a second
 * admin. They run against a running stack, never against mocks.
 */

import { expect, type Browser, type Page } from "@playwright/test";

/** The day1 service's DEV_AUTH_SECRET: the live specs skip without it. */
export const SECRET = process.env.WINGMAN_DEV_AUTH_SECRET ?? "";

/** A new browser context signed in as `username`, an admin. */
export async function loginAs(browser: Browser, username: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Dev login secret").fill(SECRET);
  await page.getByRole("combobox", { name: "Role" }).click();
  await page.getByRole("option", { name: "Admin" }).click();
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => url.pathname === "/");
  return page;
}

export async function token(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === "wingman-token")?.value ?? "";
}

/** The headers of an API call as the person signed in on `page`. */
export async function auth(page: Page) {
  return { Authorization: `Bearer ${await token(page)}` };
}

/** Open the MR a write's toast announces; `review` is the path its review page must have. */
export async function followToast(page: Page, toast: RegExp, review: RegExp): Promise<string> {
  // Earlier writes' toasts may still be up, each with its own Review button.
  const announced = page.locator("[data-sonner-toast]").filter({ hasText: toast });
  await expect(announced).toBeVisible({ timeout: 15_000 });
  await announced.getByRole("button", { name: "Review" }).click();
  await page.waitForURL(review);
  return page.url();
}

export async function approveAndMerge(page: Page, url: string) {
  await page.goto(url);
  await page.getByRole("button", { name: /review & approve/i }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve & Merge" }).click();
  await expect(page.getByText("merged", { exact: true })).toBeVisible({ timeout: 15_000 });
}
