# ADR-0054: Readiness asks GitLab only until it has answered once

Date: 2026-11-13
Status: Accepted

## Context

Both services' `/health/ready` ran a GitLab check on every probe, each under
a 3 s timeout (`wingman_core.web.app_factory`):

- day1 read the day1 project and the specs project (`get_project` twice), so
  a wrong `SPECS_GITLAB_PROJECT_ID`, or a token GitLab answers 404, does not
  look like an empty flavor list;
- day2 listed the whole sigs group (`list_group_projects`) and read the day1
  project.

The chart probes every 10 s per pod: at least 12 GitLab calls a minute per
pod, about 17,000 a day, whether or not anyone used Wingman. On the team's
sandbox, GitLab's API log showed over 800 of them and no real work.

Worse, the probe took every pod out of the Service at once when GitLab
blipped. nginx then answered 502 or 503 pages, instead of Wingman's RFC 9457
problem that says GitLab is unavailable (`GIT_UNAVAILABLE`, ADR-0004), and
the cached reads that could still have answered for up to a minute (ADR-0011,
ADR-0041) were never reached.

## Decision

- **GitLab gates readiness until it has passed once per process**
  (`ready_once`, `wingman_core.web.app_factory`). Both services wrap their
  GitLab check in it.
- **Before the first pass, the check runs on every probe, as before**: the
  same calls (day1 still reads both projects), the same 3 s timeout, and a
  failure or a timeout leaves it unpassed. A pod with a wrong URL, token, CA
  or project id never becomes ready, so a bad rollout stalls while the old
  pods keep serving.
- **After it, `/health/ready` does not call GitLab.** The check reports `ok`,
  and a later GitLab failure is reported by the request that meets it: a
  503 `GIT_UNAVAILABLE` or 502 `GIT_PERMISSION_DENIED` problem, or a cached
  answer while one is still fresh enough.
- The body keeps its shape (`{"status", "checks"}`) and its values. Probes
  that overlap before the first pass each run the check: the probe period
  is 10 s and the timeout 3 s, so sharing one in-flight check would save
  nothing worth its code.
- The warm-up (ADR-0041) is unchanged and still never holds up readiness.

## Alternatives rejected

- **Drop GitLab from readiness.** A pod that cannot read the day1 project
  would become ready and replace a good one in a rollout; every page would
  then fail.
- **Cache the check's result for a while** (say a minute). Fewer calls, but
  still calls when nobody is looking, and an outage longer than the cache
  still takes every pod out together.
- **A cheaper check** (GitLab's `/api/v4/version` or `/-/readiness`). Still a
  call per probe and still every pod out at once; and it would not catch a
  wrong project id or a token without access to it.
- **A longer probe period.** Fewer calls, the same failure mode.
- **Readiness waits for the warm-up.** The warm-up reads every repository and
  can take seconds; ADR-0041 decided readiness does not wait for it, and a
  request that arrives first joins its fetches.
- **Turn unready again when requests see GitLab fail.** That brings back the
  failure this ADR removes: every pod out of the Service at once.

## Consequences

- **An idle Wingman makes no GitLab calls.** `get_project` and
  `list_group_projects` in `wingman_dependency_requests_total` are now
  people's, rollouts', warm-ups' and refreshes', not the probe's.
- **A GitLab outage after start-up leaves the pods ready.** People see
  Wingman's own error, and cached reads answer for up to a minute.
- **A pod that starts during an outage stays unready until GitLab answers**,
  as before: a restart or a rollout during an outage still waits for GitLab.
- **The GitLab alerts follow real traffic.** `WingmanGitLabTokenRejected`
  and `WingmanGitLabUnavailable` fired within minutes from the probe's calls
  even when nobody used Wingman. Now a token revoked, or an outage, while
  Wingman is idle shows on the first request that meets it. No alert reads
  readiness: `WingmanServiceDown` is Prometheus's `up`, the scrape of
  `/metrics`, which never checks GitLab.
- **`gitlab: ok` means "GitLab answered since this pod started"**, not "GitLab
  answers now". To check GitLab now, read the counters or the requests'
  problems (`docs/ops/runbook.md`).
- Nothing to do on upgrade: the probe paths, periods and timeouts are the
  chart's, unchanged.

## Verification

- `packages/wingman-core/tests/unit/web/test_app_factory.py`: a `ready_once`
  check fails until its first pass and is asked on every probe until then;
  after it, a pass without running the check, whatever the dependency does;
  the timeout still applies before the first pass, and a timeout is not a
  pass; a check not wrapped keeps running.
- `apps/day1-service/tests/unit/test_main.py`
  (`test_without_the_specs_project_day1_is_not_ready_until_gitlab_has_both`):
  not ready while the specs project is missing, ready once both answer, and
  no project read after that.
- `apps/day2-service/tests/unit/test_settings_and_main.py`
  (`test_readiness_asks_gitlab_only_until_it_has_answered_once`): three probes
  cost one `list_group_projects` and one `get_project`.
