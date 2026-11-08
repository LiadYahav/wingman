# A merge gate on the approvals page

**Status:** proposed. The ecosystem plan's phase 2 says it already: after
the push, track the platform-config pipeline and the allocate-segment run,
and only then mark the MR ready to merge.

## The problem

A new cluster's MR is not ready when Wingman opens it. Before a merge is safe:
- the platform-config CI must have rendered and validated it;
- the allocate-segment workflow must have written `vlanId` and `dhcp_values`;
- CI must have written `mcConfigMap`.

Today the approvals page lets an admin merge as soon as the MR exists.

## Proposal

The approvals page shows the MR's checks, and **Approve & merge** waits for
them:

| Check | Read from |
|---|---|
| The pipeline on the reviewed head passed | GitLab |
| A new cluster has `vlanId` and `dhcp_values` | the file on the branch |
| No commit landed after the one reviewed | the branch head (ADR-0006 already refuses a moved head) |

A failed check shows its reason and a link: the pipeline job, or the
allocate-segment run (workflow-runs.md). An admin can override with a
recorded reason, for the day CI is down.

## Open questions

- Which pipeline jobs are required, and which are advisory?
- Is an override allowed at all, or is a failed pipeline always a stop?
