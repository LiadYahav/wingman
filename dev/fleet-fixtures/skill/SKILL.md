---
name: server-scan-api
description: Queries the Server Scan REST API to answer questions about the bare-metal server fleet - list or count servers by vendor, site, health or cluster, look up one server, read audit events. Use whenever the user asks for servers ("all Dell servers in site1", "which servers are available", "what changed on server-12") or mentions Server Scan, the inventory API, or the fleet.
when_to_use: Also for questions about a server's BMC address, MACs, maintenance state or why its health changed.
allowed-tools: Bash(curl *) Bash(jq *)
---

# Server Scan API

A short stand-in for server-scan's own skill (`.claude/skills/server-scan-api`
in team-redbull/server-scan), served by Wingman's fake server-scan
(`DAY1_FAKE_FLEET=true`) so the Claude page has something to show. You answer
fleet questions by building `curl` requests, never by guessing.

## Connection - edit these two lines for your environment

```
BASE_URL=https://server-scan.example.internal
AUDITOR_TOKEN=REPLACE_WITH_AUDITOR_TOKEN
```

Create your own token on the server's **Claude Skill** page in the UI (it is
tied to you and read-only). Pass it only in the `Authorization` header.

```bash
api() { curl -sS -H "Authorization: Bearer $AUDITOR_TOKEN" -H "Accept: application/json" "$BASE_URL$1"; }
```

## Choose the endpoint

| The user wants | Call |
|---|---|
| Servers matching vendor / site / health | `GET /api/v1/servers` with filters |
| Per-site totals | `GET /api/v1/sites` |
| One server in full detail | `GET /api/v1/servers/{id}` |

### Filters

`site_id`, `vendor`, `health_overall`, `maintenance` (true/false).

## Gotchas

- Stay on GET requests.
- Page through `next_cursor` until it is empty.

## More detail

See `references/endpoints.md`.
