# Upgrade guides

How to upgrade a Wingman that is already deployed, written for an agent (or
a person) working **inside the disconnected environment**: no internet, no
access to GitHub, and no memory of how this repo was built. Each guide is
self-contained. It says what to check before touching anything, when to
stop and report instead of improvising, and how to go back.

| From | To | Guide |
|---|---|---|
| The legacy services (`src.main:app`, the chart before PR #17) | The rewrite on `wingman-core` (`wingman_day1`, `wingman_day2`) | [legacy-to-ecosystem.md](legacy-to-ecosystem.md) |
| 3.2 | 3.3: flavors v2 (enforced locks, checked machine configs, import and sync) | [3.2-to-3.3.md](3.2-to-3.3.md) |
| 3.3.0 | 3.3.1: network templates are read by the CI's name, `nm-conf-template-<hw>.bu` (3.3.0 refused every network config) | The image tag only; nothing else changes |

Releases are named by version: from 3.0.1 on, every merge to main is a
release whose version comes from its commits (ADR-0031), and you deploy that
version (`3.0.1`) as the image tag of all three images.

## Rules for every upgrade

1. **Read before you write.** Discover what runs and check every
   precondition before changing anything. Each check names its stop
   condition. When one is hit, stop and report; don't work around it.
2. **Wingman keeps no state of its own.** GitLab is its only store
   (ADR-0002), so a Helm rollback restores the old version. Changes made in
   GitLab (a new template, a moved file) go through an MR, so they can be
   reverted too.
3. **No secrets in output.** Never print a token, a client secret or the
   JWT secret into a log, a report or a file you hand back. Refer to them by
   the Secret's name and key.
4. **One step at a time,** and record what you did, the command and its
   result. That record is the report.
5. **Never create a real cluster to test an upgrade.** Wingman's Preview
   runs every check a create runs, without committing anything.

## Adding a guide

A release that needs operator steps adds a guide here, in the same commit as
the change that needs it. Name the file `<from>-to-<to>.md`, add a row above,
and follow the shape of the existing guide: what changes, what to bring in,
discover, check, change, upgrade, verify, roll back, report.
