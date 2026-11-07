# ADR-0009: Settings refuse insecure or fake-in-production configurations at start-up

Date: 2026-11-07
Status: Accepted

## Context

The legacy services fail open. With `DEV_AUTH_SECRET` empty, dev login mints
an admin token. With `GITLAB_WEBHOOK_SECRET` empty, the webhook accepts any
caller. CORS is `*` with credentials. Secrets are plain `str`, so they appear
in `repr()` and in tracebacks. Each of these is a configuration mistake that
turns into a security hole without any error.

## Decision

- Settings are pydantic-settings models with `SecretStr` for every secret and
  bounded `Field`s for every timeout.
- A validator rejects any configuration that would run insecurely, and the
  service does not start. So far: an empty `GITLAB_TOKEN`, and
  `WINGMAN_GIT_BACKEND=fake` with `WINGMAN_ENVIRONMENT=production` (the fake
  keeps everything in memory and would silently lose every change), and a
  `JWT_SECRET_KEY` shorter than 32 characters (an HS256 secret that short can
  be brute-forced offline from any one session token).
- The default environment is `production`, so forgetting to set it means the
  strictest checks, not the loosest.
- The rewritten auth, webhook and CORS settings will follow the same rule:
  empty secret means the feature is refused, not open.

## Alternatives rejected

- **Warnings in the log.** Nobody reads start-up logs of a pod that works.

## Consequences

- A misconfigured deployment fails on rollout, where it is noticed, instead of
  in production use.

## Verification

`packages/wingman-core/tests/unit/test_settings.py`.
