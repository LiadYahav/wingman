# Common changes as forms, an API for automation, and ticket links

**Status:** proposed. Checked against [architecture-fit.md](architecture-fit.md):
"common modification processes appear in the customer-facing interface as
self-service features"; requests arrive "via the self-service catalog or a
ticket"; every count is a total.

## Common changes as one form each

Today a change to an existing cluster is the raw YAML editor: anything goes,
and the reviewer must read the whole diff. The common changes deserve a form
each:

| Change | Form | Sent as |
|---|---|---|
| Scale a nodepool | the new **total** for one nodepool | one edit now; the update-nodepool workflow later (its input is a total) |
| Add or remove a node label | key and value | one edit |
| Add or remove a machine config | the config picker (flavors v2) | one edit; the MR names the reboot |
| Change the owner | the three numbers | one edit |

Each form opens a small MR whose diff is only that change, so the review is
easy. When the workflows exist, a form starts the workflow instead, and
nothing changes for the user. The raw editor stays for everything else,
admin only.

## API tokens for automation

The ticketing system, scripts and other portals should be able to ask Wingman
for the same changes without a browser. Two parts:

- **Service tokens.** Issued by an admin, each named, scoped (read, or which
  writes) and with an expiry. Every request a token makes is audited under
  its name.
- **A documented API.** The services already publish OpenAPI. Publish it
  as the contract, versioned under `/api/v1`, with the error codes
  (ADR-0004) as part of it.

Approval doesn't change: a person merges, and nobody approves their own
change, including the owner of a token.

## A ticket on every change

Every form, and the API, takes an optional ticket key. It goes into the MR
description (`mr_conventions`, ADR-0007) and shows in the audit, which can
filter by it. That ties a cluster's history to the request that caused it,
without Wingman talking to the ticketing system.

## Open questions

- Which ticket key format, and is the field required for some changes?
- Do tokens live in a GitLab-backed file (Wingman's only store) or in a
  Kubernetes Secret per token?
