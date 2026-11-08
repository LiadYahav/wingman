# ADR-0025: A chart version other than the spec's is reported, never drift

Date: 2026-11-08
Status: Accepted (supersedes in part ADR-0016); superseded in part by ADR-0033 (a locked value the file does not hold is drift too)

## Context

Drift compared each spec addon's version with the installed one and offered a
fix. Day2 now refuses a per-cluster version other than the team default unless
it is an explicit emergency pin (ADR-0022), so every version "fix" failed.

## Decision

User decision 2026-11-08. Only a missing spec addon is drift; the fix installs
it at the team's default version. An addon installed at another version is
listed in `version_differences`, does not make a cluster `drifted`, and has no
fix. Pinning one cluster stays a deliberate emergency pin in day2.

## Consequences

`GET /clusters/{name}/drift` gains `version_differences`; `addon_drift` holds
only `reason: "missing"`. The web shows the differences as information.
