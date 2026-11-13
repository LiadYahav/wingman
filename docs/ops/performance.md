# Performance: why a page is slow, and how to see it in a deployment

Where Wingman's page time goes, and the commands to confirm each cause in a
deployment. The decisions are in ADR-0011, ADR-0035 and ADR-0041. Throughout,
`<ns>` is Wingman's namespace.

## Where the time goes

| Layer | Shared by | Kept | Cold cost |
|---|---|---|---|
| The browser's query cache (`wingman-query-cache`, localStorage) | one person in one browser | 10 min; a new build drops it | each person's first visit pays the server's answer |
| day1/day2 `TtlCache` and repo snapshots | everyone on one replica | a branch head 30 s (day1) / 15 s (day2), answered stale up to a minute while it refreshes; a commit's files until the branch moves; day2's chart repo lookups (project, branches, `values.yaml`) 15 s, answered stale the same way | a new pod: one archive per repo and one history lookup per cluster (the warm-up pays it at start-up); the first add-on list, one project and one branch list per chart repo |
| MCE reads (live status, nodes) | everyone on one replica | 10 s | two hub calls per cluster on the list |

Nothing on the server is per user: GitLab is read with the service's token,
and no cache key names a user. If pages feel "cached per person", the
server's cold cost is what each person meets on their first load.

## 1. How many replicas, and are they new?

Every replica keeps its own cache. A fresh pod is cold until its warm-up
finishes.

```bash
oc -n <ns> get deploy -l app.kubernetes.io/part-of=wingman
oc -n <ns> get pods -l app.kubernetes.io/part-of=wingman -o wide
oc -n <ns> logs deploy/wingman-day1 | grep -i "warm-up\|refreshing"   # a failed warm-up or refresh, if any
```

## 2. Is it GitLab? The history lookups and their latency

`list_commits` is the history lookup behind "changed by, at". Before
ADR-0041 every merge to the day1 repo cost one per cluster. After it, a merge
costs one per file it changed, plus one per cluster when a pod starts.

With the ServiceMonitor on (`monitoring.serviceMonitor.enabled`), in Prometheus:

```promql
# History lookups per hour: before ~ clusters x merges, after ~ files changed + clusters x pod starts
sum(increase(wingman_dependency_requests_total{dependency="gitlab", operation="list_commits"}[1h]))

# What one GitLab call costs here, by operation (the bench's --latency)
histogram_quantile(0.95, sum by (le, operation) (rate(wingman_dependency_request_duration_seconds_bucket{dependency="gitlab"}[15m])))

# The cluster list, as the service serves it
histogram_quantile(0.95, sum by (le, route) (rate(wingman_http_request_duration_seconds_bucket{route="/api/day1/clusters"}[15m])))

# MCE reads per second: with many open pages, live status was 2 per cluster per page
sum by (operation) (rate(wingman_dependency_requests_total{dependency="kubernetes"}[5m]))
```

Without Prometheus, read a pod's counters directly:

```bash
oc -n <ns> port-forward deploy/wingman-day1 8001:8001 &
curl -s localhost:8001/metrics | grep -E 'operation="(list_commits|get_branch|read_archive)"'
```

## 3. One request, cold and warm

In the browser's network tab, open the cluster list and look at
`/api/day1/clusters`: **Waiting for server response** is the service, and
**Content Download** is the transfer. Right-click → *Copy as cURL*, then time
it twice from a shell:

```bash
# paste the copied command, then append:
#   -o /dev/null -s -w 'ttfb %{time_starttransfer}s  size %{size_download} B\n'
```

The first run after a merge, or on a new pod, is the cold cost; the second
is warm. With ADR-0041, both should be well under a second. The transfer
should show `content-encoding: gzip`.

To feel what a new person gets, use a private window: it starts with an
empty browser cache.

Look at what queues in front of the API calls too. The OpenShift route
serves HTTP/1.1, so the browser opens at most six connections to Wingman,
and every `?_rsc=` request (Next.js prefetching a linked page) takes one.
Lists link with `IntentLink`, which prefetches a page only once the pointer
or focus reaches its link (`apps/web/README.md`, UI conventions). Before it,
the Addons page prefetched about nine add-on pages as it loaded and its API
calls waited about 700 ms behind them. The sidebar's links still prefetch
as a page loads (two requests per page it links). Any more `?_rsc=` requests
before a page's `/api/` calls mean a bare `Link` in a list.

## 4. The same numbers on a laptop

`scripts/dev/bench_day1_reads.py` runs day1 in-process on the in-memory
GitLab, with every GitLab and MCE call waiting `--latency` seconds. Take the
latency from the second query in step 2:

```bash
uv run python scripts/dev/bench_day1_reads.py --clusters 300 --latency 0.2
```

It prints each case a person meets: cold, warm, after the TTL, the first
and next load after a merge, 20 people at once, and live status for 20 open
pages. Each line has its time, its size and its GitLab calls.
