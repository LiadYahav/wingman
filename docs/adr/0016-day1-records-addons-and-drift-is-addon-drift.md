# ADR-0016: Day1 records a spec's addons and their overrides; it never writes day2, and unknown drift is not "in sync"

Date: 2026-11-07
Status: Accepted; superseded in part by ADR-0025 (version differences) and ADR-0033 (drift also compares the flavor's locked values)

## Context

A spec lists day2 addons (`spec.day2.addons`), each with fields the creator
may override. The legacy create accepted `addon_overrides` and dropped
them; the addons were never installed and showed up later as "missing"
drift, whose "Fix" installed them with no overrides. Legacy drift also
re-rendered the template with stored inputs to diff the file, but no inputs
were stored, so YAML drift always reported "not drifted", and a failed day2
call also counted as "not drifted".

Day2 is being rewritten against the new gitops-day2 layout (env levels,
fleet defaults, exclusions, version pins); how an addon is installed there
is day2's decision.

## Decision

- At create, the spec's addons and the user's override values (keyed
  `team/name`; an override for an addon the spec does not list is a 422) are
  recorded in the cluster file's header (ADR-0012) and in the MR
  description. Day1 does not open day2 MRs or call day2's write API.
- Drift is addon drift: every spec addon must be installed (matched by
  `team/name`) at the spec's version, as day2 reports it. Each drifted addon
  carries the override values recorded at create, so installing it keeps
  them.
- A cluster whose drift cannot be determined (its spec is gone or
  unreadable, day2 did not answer) is `unknown`, `is_drifted: null`, with the
  reason. The summary returns every cluster, so one failure never hides the
  rest and never reads as "in sync".
- YAML drift and `POST /clusters/{name}/sync-yaml` are removed: without
  stored inputs there is nothing to re-render, and the file legitimately
  changes after create.
- Day1 asks day2 with its own short-lived viewer session
  (`system:wingman-day1`), not a forwarded user token, so the cached answer
  does not depend on who asked first.

## Alternatives rejected

- **Day1 opens day2 install MRs at create**: couples day1 to a day2 API that
  is being rewritten, and installs onto a cluster that does not exist until
  the day1 MR merges.
- **A day1-owned file for the addon requests**: a second file per create
  (see ADR-0012).

## Consequences

- Installing a new cluster's addons is still a day2 action, now with the
  creator's values available to it.
- Day1 depends on day2's `GET /api/day2/clusters/{name}/addons` (with `mce`
  and `site`); the day2 rewrite must keep it or `HttpDay2Addons` follows it.

## Verification

`apps/day1-service/tests/unit/application/test_drift.py` and the
addon-override regression tests in
`apps/day1-service/tests/unit/application/test_clusters.py`.
