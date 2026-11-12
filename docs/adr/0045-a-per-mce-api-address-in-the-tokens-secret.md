# ADR-0045: An MCE's API address may be given beside its token, in the tokens Secret

Date: 2026-11-12
Status: Accepted; extends ADR-0019 (how a hub is reached)

## Context

Day1 reads every MCE hub at an address it builds from the MCE's folder name,
`https://api.<mce>.<MCE_API_DOMAIN>:6443` (ADR-0019), with that MCE's
service-account token from `MCE_TOKENS_FILE`, a YAML map of MCE name to
token mounted from a Secret.

Some hubs do not follow that pattern. The team's sandbox hub is one
(single-pane.md, workstream 1): its API is not at `api.<folder name>`. Live
status, the InfraEnv list, the nodes view (ADR-0038) and MCE placement's free
pods (ADR-0050) all read the hub, so on such a hub none of them can work.

## Decision

- **An entry of the tokens file may be a mapping** with `token` and an
  optional `url`:

  ```yaml
  ocp4-prod-mce-site1-a: <token>
  ocp4-prod-mce-site1-b:
    token: <token>
    url: https://api.hub-b.example.com:6443
  ```

  The plain form, MCE name to token, is unchanged and still the usual one.
- **A `url` is `https://<host>[:<port>]` and nothing more.** A path, a
  query, a fragment or credentials would change every read's request, and a
  plain `http://` hub would receive the token in the clear. Anything else
  stops day1 at start (ADR-0009), with a message that names the MCE and never
  the token. An unknown key in the mapping is refused too, so a misspelt
  `url` is not silently the convention.
- **The address is per hub, not per read.** `HttpHubApi` builds one client
  per MCE at its `url`, or at the convention's address when it has none, so
  every read of the hub (live status, InfraEnvs, nodes, placement) uses it.
- No new setting: the address lives with the token, in the same Secret.

## Alternatives rejected

- **A separate setting or ConfigMap of addresses** (`MCE_API_URLS`): two
  lists of MCEs to keep in step, and a hub whose token moves but whose address
  does not is half-configured. The Secret already names every hub Wingman may
  read.
- **A domain per MCE**: the sandbox's hub is not `api.<name>` under any
  domain, so a domain alone does not reach it.
- **Reading each hub's address from the platform's ArgoCD cluster Secrets**:
  that is a read of Secrets on the platform's hub, a far larger grant than a
  hub's own reads, for something an operator writes once.

## Consequences

- An operator adds a hub off the pattern by editing the Secret, and restarts
  day1, which reads the file at start (as for a new token).
- The 3.3-to-3.4 guide's one-liners that print MCE names and tokens read the
  plain form only; the upgrade guide of this release says how to read a
  mapping entry.
- The convention stays the default, so every deployed Secret keeps working
  unchanged.

## Verification

`apps/day1-service/tests/unit/infrastructure/test_hub_api.py`:
`test_load_mce_access_reads_an_mce_with_its_own_address` (both forms in one
file), `test_load_mce_access_refuses_bad_files_without_echoing_tokens` (a
missing token, an unknown key, `http://`, a path, a query, credentials, a
port that is not a number, no host; never the token in the message), and
`test_an_mce_with_its_own_address_is_read_there_with_its_token` (the request
goes to the given address with that MCE's token, the others to the
convention's).
