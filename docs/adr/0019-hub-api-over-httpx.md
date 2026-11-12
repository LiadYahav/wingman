# ADR-0019: MCE hubs, OpenShift OAuth and day2 are reached over httpx, behind ports, with failures reported

Date: 2026-11-07
Status: Accepted; a hub may have its own address in the tokens Secret (ADR-0045)

## Context

The legacy service read HostedClusters, NodePools and InfraEnvs from each
MCE hub with the synchronous `kubernetes` client inside `asyncio.to_thread`
(the trap ADR-0002 describes for GitLab), skipped clusters whose status
failed in the bulk call, and returned 200 with a healthy-looking body for
some errors. OpenShift OAuth used ad-hoc httpx calls without timeouts and
built the authorize URL without encoding. Day2 was called with the user's
forwarded token and any failure counted as "no addons".

## Decision

- Three ports with an httpx adapter and a fake each: `HubApi`
  (`HttpHubApi`: one client per MCE at `https://api.<mce>.<MCE_API_DOMAIN>:6443`
  with the MCE's service-account token from `MCE_TOKENS_FILE`),
  `IdentityProvider` (`OpenShiftOAuth`: discovery, code exchange,
  `users/~`), `Day2Addons` (`HttpDay2Addons`). Every request has a timeout;
  TLS verification is on by default (`*_SSL_VERIFY` may name a CA bundle).
- Failures are typed domain errors (not configured, not found, denied,
  unavailable) and are counted in `wingman_dependency_*` with
  `dependency="kubernetes"|"openshift_oauth"|"day2"` (ADR-0010). No token,
  client secret or code appears in an error or a log.
- Live status stays off by default (`CLUSTER_STATUS_ENABLED`); its routes
  answer 501 `FEATURE_DISABLED` when off. A hub that cannot be read gives a
  status with `error`, and the bulk call answers for every cluster asked.
- Login: someone in no Wingman group gets 403; dev login exists only with a
  32-character secret (settings refuse to start otherwise) and compares it
  in constant time; with neither OAuth nor dev login configured the service
  refuses to start (ADR-0009).

## Alternatives rejected

- **Keep the kubernetes client in a thread**: the abandoned-thread problem,
  and a heavy dependency for three GET calls.

## Consequences

- The `kubernetes` package is gone from day1's dependencies.
- A hub reached through a private CA needs `MCE_SSL_VERIFY=<bundle path>`;
  the legacy default was `false`.

## Verification

`apps/day1-service/tests/unit/infrastructure/test_hub_api.py`,
`test_openshift_oauth.py`, `test_day2_client.py` (request shapes, error
mapping, secrets absent from errors, metrics), `test_settings.py`
(fail-closed login settings) and the status API tests.
