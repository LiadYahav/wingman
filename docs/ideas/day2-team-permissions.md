# Day2 permissions per team

**Status:** proposed.

## The problem

Every write in Wingman needs the admin group (`WINGMAN_ADMIN_GROUPS`,
`AdminUser`). Day2 is organised by team: each team has its own `sigs/<team>`
repo. Today, either a team member is an admin of everything, or they can't
change their own add-ons.

## Proposal

- A day2 write to `sigs/<team>` is allowed for an admin, or for a member of
  that team's OpenShift group.
- A mapping from team to group, in settings, for example
  `WINGMAN_TEAM_GROUPS={"redbull": ["redbull-devs"]}`. Or a convention, such
  as the group `wingman-team-<team>`.
- Groups already travel in the app JWT, so the check is local: a new
  dependency, `TeamWriter(team)`, beside `AdminUser`.
- Reads stay open to every signed-in user.
- Day1 stays admin-only: a cluster belongs to the platform, not to a team.
- Approval stays as it is: nobody approves their own change. Whether an
  approver must also be in the team is an open question.

## Open questions

- A mapping in settings, or a naming convention for the groups?
- Can a team member approve another team member's change, or only an admin?
