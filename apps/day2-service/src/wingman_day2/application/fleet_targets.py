"""One env's and one destination's values of a fleet default (ADR-0053).

The MCE, hosted-cluster and UPI defaults layer, lowest first:
``values.yaml`` (every destination), ``values-<env>.yaml`` (one env: prod,
prep or test) and ``values-<name>.yaml`` (one destination), below the
destination's own MCE-wide or UPI-wide and cluster-wide files: env before
cluster, and the cluster wins (``domain.stacks``, checked by the oracle). The
hub is one destination: its values are the default's own ``values.yaml``.
Which add-ons a hosted cluster has of its own is its flavor's and the create
form's, not the default's.

Wingman does not write ``exclusions.yaml`` (ADR-0053's amendment of
2026-11-12): an add-on wanted on some MCEs only is installed in each one's
own folder (``ChangeService.install_on_mces``), not excluded from a default.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from wingman_core.domain.mr_conventions import Repo, ResourceType, Verb, mr_title
from wingman_core.domain.users import User
from wingman_day2.application.plan_writer import (
    SCOPE_LABELS,
    SCOPE_NOUNS,
    Action,
    AuthoringPlan,
    AuthoringResult,
    PlanWriter,
    fleet_apps,
    tweak_path,
)
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ALLOWED_ENVS, DefaultsScope
from wingman_day2.domain.errors import ChangeRefusedError, ChartNotInstalledError
from wingman_day2.domain.findings import Rule, warning

OVERRIDE_SCOPES = (DefaultsScope.MCES, DefaultsScope.HOSTED_CLUSTERS, DefaultsScope.UPI)
"""The scopes whose envs and destinations get values of their own from the add-on's page."""


def _refuse_scope(scope: DefaultsScope) -> None:
    if scope not in OVERRIDE_SCOPES:
        raise ChangeRefusedError(
            f"{SCOPE_LABELS[scope]}: the hub is one destination, its values are the default's "
            "own values.yaml",
            details={"rule": "override-scope", "scope": str(scope)},
        )


class FleetTargetService(PlanWriter):
    """Plan and open the MRs that give one destination of a fleet default its own values."""

    async def set_destination_values(
        self,
        team: str,
        chart: str,
        scope: DefaultsScope,
        cluster: str,
        values: Mapping[str, object] | None,
        user: User,
        *,
        last_commit_id: str | None = None,
        confirm_changes: Sequence[str] = (),
        expected_digest: str | None = None,
        dry_run: bool = False,
        message: str | None = None,
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR setting a destination's values file.

        The file is ``values-<name>.yaml`` in the default's folder; empty values delete it.
        """
        topology = await self._topology.load()
        state = topology.team(team)
        await self._access.require_write(state.team)
        _refuse_scope(scope)
        if not state.repo.tree.is_dir(layout.defaults_dir(scope).child(chart)):
            raise ChartNotInstalledError(
                f"{chart} is not a fleet default of {team} on {SCOPE_LABELS[scope]}",
                details={"team": team, "chart": chart, "scope": str(scope)},
            )
        destinations = {
            d.ref.id: d for d in state.plan.destinations if d.ref.defaults_scope is scope
        }
        destination = destinations.get(cluster)
        if destination is None:
            raise ChangeRefusedError(
                f"{cluster} is not a destination of {SCOPE_LABELS[scope]} that {team}'s repo "
                f"registers (have: {', '.join(sorted(destinations)) or 'none'})",
                details={"rule": "destination-unknown", "cluster": cluster},
            )
        ref = destination.ref
        if ref.exclusion_key in ALLOWED_ENVS:
            raise ChangeRefusedError(
                f"values-{ref.exclusion_key}.yaml is the {ref.exclusion_key} env layer of the "
                f"default, read by every {SCOPE_NOUNS[scope]} in {ref.exclusion_key}: a "
                f"destination named {ref.exclusion_key} cannot have values of its own there",
                details={"rule": "override-name-is-env", "cluster": ref.id},
            )
        plan = AuthoringPlan(state, Action.OVERRIDE_VALUES, chart, scope)
        path = tweak_path(scope, chart, ref)
        await self.plan_values(plan, path, values or {}, last_commit_id, delete_when_empty=True)
        if not plan.changes:
            raise ChangeRefusedError(
                f"nothing to change: {path} already holds this", details={"rule": "no-change"}
            )
        after = await self.validate(topology, plan)
        plan.reach = [
            a.ref
            for a in fleet_apps(after, chart, scope)
            if a.ref.exclusion_key == ref.exclusion_key
        ]
        shared = [
            d.ref
            for d in destinations.values()
            if d.ref != ref and d.ref.exclusion_key == ref.exclusion_key
        ]
        if shared:
            plan.notes.append(
                f"{path.name} is read by every {SCOPE_NOUNS[scope]} named {ref.exclusion_key}: "
                f"{', '.join(r.id for r in shared)} gets it too."
            )
        if not any(a.ref == ref for a in after.apps if a.chart == chart):
            plan.findings.append(
                warning(
                    Rule.EXCLUSIONS_UNKNOWN_TARGET,
                    f"the default does not deploy {chart} to {ref.name} (the platform renders "
                    f"nothing there, or the repo's exclusions.yaml keeps it off): {path.name} "
                    "applies once it does",
                    team=team,
                    chart=chart,
                    cluster=ref.id,
                )
            )
        plan.notes.append(
            f"{path} sits above the default's values.yaml and values-{ref.env}.yaml and below "
            f"{ref.name}'s own MCE-wide and cluster-wide files. "
            "Leaves that are manual-sync deploy the change only when someone syncs them."
        )
        extra = f"values on {ref.name}" + ("" if values else ": back to the fleet default")
        plan.title = mr_title(
            Repo.DAY2,
            Verb.OVERRIDE,
            ResourceType.ADDON,
            f"{team}/{chart}",
            f"{extra} (fleet default on {SCOPE_LABELS[scope]})",
        )
        self.confirm(plan, confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)

    async def set_env_values(
        self,
        team: str,
        chart: str,
        scope: DefaultsScope,
        env: str,
        values: Mapping[str, object] | None,
        user: User,
        *,
        last_commit_id: str | None = None,
        confirm_changes: Sequence[str] = (),
        expected_digest: str | None = None,
        dry_run: bool = False,
        message: str | None = None,
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR setting one env's values of a fleet default.

        The file is ``values-<env>.yaml`` in the default's folder, read by
        every destination of the scope in that env; empty values delete it.
        """
        topology = await self._topology.load()
        state = topology.team(team)
        await self._access.require_write(state.team)
        _refuse_scope(scope)
        if env not in ALLOWED_ENVS:
            raise ChangeRefusedError(
                f"{env!r} is not an env the platform knows ({', '.join(sorted(ALLOWED_ENVS))})",
                details={"rule": "env-unknown", "env": env},
            )
        if not state.repo.tree.is_dir(layout.defaults_dir(scope).child(chart)):
            raise ChartNotInstalledError(
                f"{chart} is not a fleet default of {team} on {SCOPE_LABELS[scope]}",
                details={"team": team, "chart": chart, "scope": str(scope)},
            )
        plan = AuthoringPlan(state, Action.OVERRIDE_VALUES, chart, scope)
        path = layout.defaults_dir(scope).child(chart, f"values-{env}.yaml")
        await self.plan_values(plan, path, values or {}, last_commit_id, delete_when_empty=True)
        if not plan.changes:
            raise ChangeRefusedError(
                f"nothing to change: {path} already holds this", details={"rule": "no-change"}
            )
        after = await self.validate(topology, plan)
        plan.reach = [a.ref for a in fleet_apps(after, chart, scope) if a.ref.env == env]
        named = [
            d.ref.id
            for d in state.plan.destinations
            if d.ref.defaults_scope is scope and d.ref.exclusion_key == env
        ]
        if named:
            plan.findings.append(
                warning(
                    Rule.EXCLUSIONS_UNKNOWN_TARGET,
                    f"{', '.join(named)} is named {env}: {path.name} is its values-<name>.yaml "
                    "too, read above every other destination's env file",
                    team=team,
                    chart=chart,
                    path=str(path),
                )
            )
        plan.notes.append(
            f"{path} is read by every {SCOPE_NOUNS[scope]} of {team} in {env} "
            f"({len(plan.reach)} today): above the default's values.yaml, below each "
            "destination's own values-<name>.yaml and its MCE-wide or UPI-wide and cluster-wide "
            "files. Leaves that are manual-sync deploy the change only when someone syncs them."
        )
        extra = f"values for {env}" + ("" if values else ": back to the fleet default")
        plan.title = mr_title(
            Repo.DAY2,
            Verb.OVERRIDE,
            ResourceType.ADDON,
            f"{team}/{chart}",
            f"{extra} (fleet default on {SCOPE_LABELS[scope]})",
        )
        self.confirm(plan, confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)
