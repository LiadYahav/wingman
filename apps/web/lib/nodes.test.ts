import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nodesQuery } from "./nodes";

/** day1's answer for a cluster the MCE does not have yet. */
const notFound = () =>
  new Response(JSON.stringify({ status: 404, code: "NOT_FOUND", detail: "the MCE has no HostedCluster ocp4-prod-new-site1" }), {
    status: 404,
    headers: { "Content-Type": "application/problem+json" },
  });

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A component on the nodes read, as React mounts one for an admin (or `admin: false`, a viewer): an observer, subscribed. */
function mount(client: QueryClient, { admin = true }: { admin?: boolean } = {}) {
  const observer = new QueryObserver(client, nodesQuery("ocp4-prod-new-site1", "?site=site1&mce=ocp4-prod-mce-site1-a", { admin }));
  const unmount = observer.subscribe(() => {});
  return { observer, unmount };
}

describe("the nodes read", () => {
  it("fails once: a component that mounts on the failed read later does not read it again", async () => {
    const fetch = vi.fn(async () => notFound());
    vi.stubGlobal("fetch", fetch);
    const client = new QueryClient();
    const tab = mount(client);
    await vi.waitFor(() => expect(tab.observer.getCurrentResult().status).toBe("error"));
    expect(fetch).toHaveBeenCalledTimes(1);

    // The scale-down's server picker, mounted and unmounted again and again
    for (let i = 0; i < 5; i++) {
      const picker = mount(client);
      expect(picker.observer.getCurrentResult()).toMatchObject({ status: "error", fetchStatus: "idle" });
      picker.unmount();
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetch).toHaveBeenCalledTimes(1);
    tab.unmount();
    client.clear();
  });

  it("is read again by its Retry", async () => {
    const fetch = vi.fn(async () => notFound());
    vi.stubGlobal("fetch", fetch);
    const client = new QueryClient();
    const tab = mount(client);
    await vi.waitFor(() => expect(tab.observer.getCurrentResult().status).toBe("error"));
    await tab.observer.refetch();
    expect(fetch).toHaveBeenCalledTimes(2);
    tab.unmount();
    client.clear();
  });

  it("is never sent for a viewer, wherever it is mounted (ADR-0038, amended 2026-11-23)", async () => {
    const fetch = vi.fn(async () => notFound());
    vi.stubGlobal("fetch", fetch);
    const client = new QueryClient();
    const card = mount(client, { admin: false });
    const picker = mount(client, { admin: false });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(card.observer.getCurrentResult()).toMatchObject({ status: "pending", fetchStatus: "idle" });
    expect(fetch).not.toHaveBeenCalled();
    card.unmount();
    picker.unmount();
    client.clear();
  });
});
