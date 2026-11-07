# Session log

Newest first. Each entry is the "Where to continue right now" section of
`CLAUDE.md` as it stood when the next unit of work started. Together with
`git log` and the ADRs each entry names, this is the record of the work.

**2026-11-07 — ecosystem map, the new day1 template, the UI refresh.**
`docs/ecosystem/` maps server-scan, segments-manager, the Temporal workflows,
herzi, the hostedclusters-setup chart, gitops-day2 and kubevirt-workflows,
and how Wingman fits them. The new `cluster-template.j2` renders the slim
values file and was checked with `helm template` against both chart copies.
Earlier the same day: the dark-first UI refresh (PR #16) and the legacy
Playwright specs fixed.
