# Owner-scoped access and showback

**Status:** proposed. Builds on the owner numbers (merkaz, anaf, mador;
flavors v2, ADR-0028) and on the architecture's tenants: they consume
clusters, are read-only on them, and ask for changes through the catalog.

## Tenants see their own clusters

Today Wingman has two roles, admin and viewer, and both see everything. A
tenant role would see and request changes only for the clusters whose
`owner` matches theirs:

- A mapping from OpenShift group to owner numbers, for example a group per
  mador, or per anaf (all its madors).
- Lists, pages and the audit filter to the tenant's clusters. Requests (the
  forms in self-service-changes.md) are allowed on those clusters only.
- Approval stays with admins. A tenant asks; the platform team merges.

This is the same check as day2 permissions per team
(day2-team-permissions.md), keyed on the owner instead of the team. Build
them together.

## Showback per owner

How much capacity each org unit holds: nodes by node type, summed per mador,
anaf and merkaz, from the NodePools' replicas (what is asked for) and
server-scan (what runs). Read-only, for planning and for conversations about
who holds what.

## Open questions

- Is a group per mador enough, or do tenants span several?
- Does a tenant see the whole fleet read-only (as viewers do today), or only
  their own?
