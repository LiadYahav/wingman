"""Which destinations a fleet default reaches, and what one of them gets (ADR-0053).

Three writes on one fleet default ``defaults/<scope>/<chart>/``, one MR each:

- **exclusions**: the scope's ``exclusions.yaml`` lists, per chart, the names
  the default skips. Wingman sets the chart's list to exactly the requested
  destinations, in place (``domain.exclusions.set_excluded``: every comment
  line kept). Excluding deletes the destination's Application; the platform
  apps are ``prune: false`` with no resources finalizer, so the workload is
  orphaned, still running. Including generates it again, and the new
  Application adopts what still runs.
- **values for one destination**: ``values-<name>.yaml`` in the default's
  folder, layered above the default's ``values.yaml`` and ``values-<env>.yaml``
  for every app of that chart on a destination of that name.
- **deploy config for one destination**: the platform's full-override
  carve-out. The deploy-config stack has no per-destination layer in the
  defaults folder; the only per-destination layer is the destination's own
  ``<chart>/<chart>.yaml``, and a folder there is the XOR rule's duplicate
  unless the destination is excluded. So Wingman excludes it and writes its
  own deploy config in one commit; both generators name the Application the
  same, so ArgoCD keeps it. Removing the override moves the own folder back
  into the default (as adoption does) and drops the exclusion entry.

The hub has neither: it is one cluster, its default is its own folder.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from wingman_core.domain.git import FileChange, FileContent
from wingman_core.domain.mr_conventions import Repo, ResourceType, Verb, mr_title
from wingman_core.domain.users import User
from wingman_day2.application.authoring import check_namespace
from wingman_day2.application.plan_writer import (
    SCOPE_LABELS,
    SCOPE_NOUNS,
    Action,
    AuthoringPlan,
    AuthoringResult,
    Effect,
    PlanWriter,
    fleet_apps,
    tweak_path,
)
from wingman_day2.application.topology import TeamState, Topology
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import ALLOWED_ENVS, ClusterRef, DefaultsScope
from wingman_day2.domain.deploy_config import (
    PATH,
    PROJECT_NAMESPACE,
    REPOURL,
    TARGET_REVISION,
    truthy,
)
from wingman_day2.domain.errors import ChangeRefusedError, ChartNotInstalledError
from wingman_day2.domain.exclusions import LAYOUT_RULE, set_excluded
from wingman_day2.domain.findings import Rule, warning
from wingman_day2.domain.platform import AppSource, Destination, PlannedApp, scope_exclusions
from wingman_day2.domain.yaml_text import dump_yaml, edit_mapping_text, same_value
from wingman_day2.domain.yaml_values import parse_values

DEPLOY_OVERRIDE_KEYS = (TARGET_REVISION, REPOURL, PATH, PROJECT_NAMESPACE)
"""The keys a per-destination deploy config may set."""

_LISTED = 3


def _names(refs: Sequence[ClusterRef], scope: DefaultsScope) -> str:
    if len(refs) > _LISTED:
        return f"{len(refs)} {SCOPE_NOUNS[scope]}"
    return ", ".join(r.name for r in refs)


class FleetTargetService(PlanWriter):
    """Plan and open the MRs that choose and tune a fleet default's destinations."""

    async def _load(
        self, team: str, chart: str, scope: DefaultsScope
    ) -> tuple[Topology, TeamState, dict[str, Destination]]:
        topology = await self._topology.load()
        state = topology.team(team)
        await self._access.require_write(state.team)
        if scope is DefaultsScope.HUB:
            raise ChangeRefusedError(
                "the hub is one cluster and its fleet default is its own folder: there are no hub "
                "exclusions or per-destination overrides; edit the default itself",
                details={"rule": "hub-override"},
            )
        if not state.repo.tree.is_dir(layout.defaults_dir(scope).child(chart)):
            raise ChartNotInstalledError(
                f"{chart} is not a fleet default of {team} on {SCOPE_LABELS[scope]}",
                details={"team": team, "chart": chart, "scope": str(scope)},
            )
        destinations = {
            d.ref.id: d for d in state.plan.destinations if d.ref.defaults_scope is scope
        }
        return topology, state, destinations

    @staticmethod
    def _destination(
        destinations: Mapping[str, Destination], cluster: str, scope: DefaultsScope, team: str
    ) -> Destination:
        found = destinations.get(cluster)
        if found is None:
            raise ChangeRefusedError(
                f"{cluster} is not a destination of {SCOPE_LABELS[scope]} that {team}'s repo "
                f"registers (have: {', '.join(sorted(destinations)) or 'none'})",
                details={"rule": "destination-unknown", "cluster": cluster},
            )
        return found

    async def _exclusions_file(
        self, plan: AuthoringPlan, scope: DefaultsScope
    ) -> tuple[FileContent | None, list[str]]:
        """The scope's exclusions file and the names it lists for the plan's chart."""
        path = layout.exclusions_file(scope)
        tree = plan.state.repo.tree
        file = await self._sigs.read(plan.state.team, path) if tree.is_file(path) else None
        current = scope_exclusions(plan.state.repo, scope)
        if current is None:
            raise ChangeRefusedError(
                f"{path} does not read as exclusions (the platform fails every app of "
                f"{SCOPE_LABELS[scope]} on it); fix it by hand first",
                details={"rule": LAYOUT_RULE, "path": str(path)},
            )
        return file, list(current.names(plan.chart))

    def _write_exclusions(
        self,
        plan: AuthoringPlan,
        scope: DefaultsScope,
        file: FileContent | None,
        names: Sequence[str],
        last_commit_id: str | None,
    ) -> bool:
        """Set the chart's list to ``names``; whether the file changes."""
        path = layout.exclusions_file(scope)
        old = file.content if file else None
        text = set_excluded(old, plan.chart, names, path=str(path))
        if text is None or text == old:
            return False
        self.write(plan, path, text, file, last_commit_id)
        return True

    # ── exclusions ──────────────────────────────────────────────────────────

    async def set_exclusions(
        self,
        team: str,
        chart: str,
        scope: DefaultsScope,
        excluded: Sequence[str],
        user: User,
        *,
        last_commit_id: str | None = None,
        confirm_changes: Sequence[str] = (),
        expected_digest: str | None = None,
        dry_run: bool = False,
        message: str | None = None,
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR making the default skip exactly ``excluded``.

        ``excluded`` are destination ids of the scope. Names the entry lists
        that are no destination of the team stay as written.
        """
        topology, state, destinations = await self._load(team, chart, scope)
        plan = AuthoringPlan(state, Action.SET_EXCLUSIONS, chart, scope)
        wanted = [self._destination(destinations, c, scope, team) for c in dict.fromkeys(excluded)]
        wanted_ids = {d.ref.id for d in wanted}
        by_key: dict[str, list[Destination]] = {}
        for d in destinations.values():
            by_key.setdefault(d.ref.exclusion_key or "", []).append(d)
        for d in wanted:
            others = [
                o.ref.id for o in by_key[d.ref.exclusion_key or ""] if o.ref.id not in wanted_ids
            ]
            if others:
                raise ChangeRefusedError(
                    f"exclusions.yaml lists names, and {d.ref.exclusion_key} names "
                    f"{len(others) + 1} destinations ({d.ref.id}, {', '.join(others)}): they are "
                    "excluded together or not at all",
                    details={"rule": "exclusion-shared", "clusters": [d.ref.id, *others]},
                )
        file, listed = await self._exclusions_file(plan, scope)
        if file is None:
            await self.refuse_if_deleted(plan, layout.exclusions_file(scope), last_commit_id)
        keys = [d.ref.exclusion_key or "" for d in wanted]
        unknown = [n for n in listed if n not in by_key]
        names = [n for n in listed if n in keys or n in unknown] + [
            k for k in keys if k not in listed
        ]
        tree = state.repo.tree
        for key in listed:
            for d in by_key.get(key, []) if key not in keys else []:
                if tree.is_dir(layout.chart_dir(d.ref, chart)):
                    raise ChangeRefusedError(
                        f"{d.ref.name} has its own deploy config for {chart} "
                        f"({layout.chart_dir(d.ref, chart)}/), deployed in place of the default: "
                        "including it would generate the app twice. Remove its own deploy "
                        "config instead; that includes it again.",
                        details={"rule": "own-deploy", "cluster": d.ref.id},
                    )
        if not self._write_exclusions(plan, scope, file, names, last_commit_id):
            raise ChangeRefusedError(
                f"nothing to change: {layout.exclusions_file(scope)} already lists exactly these",
                details={"rule": "no-change"},
            )
        if unknown:
            plan.findings.append(
                warning(
                    Rule.EXCLUSIONS_UNKNOWN_TARGET,
                    f"{layout.exclusions_file(scope)} lists {', '.join(unknown)} for {chart}, "
                    f"which is no {SCOPE_NOUNS[scope]} of {team}: kept as written",
                    team=team,
                    chart=chart,
                    path=str(layout.exclusions_file(scope)),
                )
            )
        after = await self.validate(topology, plan)
        plan.reach = [a.ref for a in fleet_apps(after, chart, scope)]
        out = [i for i in plan.impact if i.effect is Effect.REMOVED]
        back = [i for i in plan.impact if i.effect is Effect.ADDED]
        if out:
            plan.notes.append(
                f"Excluding deletes {', '.join(i.app_name for i in out)} from ArgoCD, but the "
                "platform's apps are prune: false with no resources finalizer, so ArgoCD orphans "
                f"the workload: {chart} keeps running on {', '.join(i.ref.name for i in out)}, "
                "unmanaged. An exclusion is prevention, not teardown: tear it down by hand after "
                "the merge if it must go (runbook R10)."
            )
        if back:
            plan.notes.append(
                f"Including generates {', '.join(i.app_name for i in back)} again; if the "
                "workload still runs there, the new Application adopts it in place."
            )
        newly_out = [i.ref for i in out]
        newly_in = [i.ref for i in back]
        label = SCOPE_LABELS[scope]
        if newly_out and not newly_in:
            verb, extra = (
                Verb.EXCLUDE,
                f"from {_names(newly_out, scope)} (fleet default on {label})",
            )
        elif newly_in and not newly_out:
            verb, extra = Verb.INCLUDE, f"on {_names(newly_in, scope)} (fleet default on {label})"
        else:
            verb, extra = Verb.UPDATE, f"exclusions (fleet default on {label})"
        plan.title = mr_title(Repo.DAY2, verb, ResourceType.ADDON, f"{team}/{chart}", extra)
        self.confirm(plan, confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)

    # ── values for one destination ──────────────────────────────────────────

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
        topology, state, destinations = await self._load(team, chart, scope)
        destination = self._destination(destinations, cluster, scope, team)
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
                    f"the default does not deploy {chart} to {ref.name} (it is excluded or not "
                    f"rendered): {path.name} applies once it does",
                    team=team,
                    chart=chart,
                    cluster=ref.id,
                )
            )
        deleting = not values
        plan.notes.append(
            f"{path} sits above the default's values.yaml and values-{ref.env}.yaml and below "
            f"{ref.name}'s own MCE-wide and cluster-wide files. "
            "Leaves that are manual-sync deploy the change only when someone syncs them."
        )
        extra = f"values on {ref.name}" + (": back to the fleet default" if deleting else "")
        plan.title = mr_title(
            Repo.DAY2,
            Verb.OVERRIDE,
            ResourceType.ADDON,
            f"{team}/{chart}",
            f"{extra} (fleet default on {SCOPE_LABELS[scope]})",
        )
        self.confirm(plan, confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)

    # ── deploy config for one destination ───────────────────────────────────

    async def set_destination_deploy(
        self,
        team: str,
        chart: str,
        scope: DefaultsScope,
        cluster: str,
        deploy: Mapping[str, object | None] | None,
        user: User,
        *,
        last_commit_id: str | None = None,
        confirm_changes: Sequence[str] = (),
        expected_digest: str | None = None,
        dry_run: bool = False,
        message: str | None = None,
    ) -> AuthoringResult:
        """Plan, and unless ``dry_run`` open, the MR giving a destination its own deploy config.

        The destination is excluded from the default and deployed from its own
        folder; ``None`` takes it back into the default.
        """
        topology, state, destinations = await self._load(team, chart, scope)
        destination = self._destination(destinations, cluster, scope, team)
        ref = destination.ref
        if not destination.renders or not ref.env_allowed:
            raise ChangeRefusedError(
                f"the platform renders nothing for {ref.name} (no day1 version, or an env it "
                "does not accept): a folder for it would be a phantom",
                details={"rule": str(Rule.DAY1_VERSION_MISSING), "cluster": ref.id},
            )
        plan = AuthoringPlan(state, Action.OVERRIDE_DEPLOY, chart, scope)
        file, listed = await self._exclusions_file(plan, scope)
        key = ref.exclusion_key or ""
        own = layout.chart_dir(ref, chart)
        tree = state.repo.tree
        fleet = layout.defaults_dir(scope).child(chart)
        if deploy is None:
            if not tree.is_dir(own):
                raise ChangeRefusedError(
                    f"{ref.name} has no deploy config of its own for {chart} ({own}/)",
                    details={"rule": "no-change"},
                )
            plan.adopted.append(await self.adopt(plan, destination, fleet))
            self._write_exclusions(plan, scope, file, [n for n in listed if n != key], None)
            plan.notes.append(
                f"{own}/ moves back into the default in this MR and {key} leaves "
                f"{layout.exclusions_file(scope)}: the Application keeps its name, ArgoCD keeps "
                "it, and it follows the default's deploy config again."
            )
            extra = f"deploy config on {ref.name}: back to the fleet default"
        else:
            await self._plan_own_deploy(plan, destination, deploy, last_commit_id)
            if key not in listed:
                self._write_exclusions(plan, scope, file, [*listed, key], None)
            plan.notes.append(
                f"{ref.name} leaves the default ({key} in {layout.exclusions_file(scope)}) and "
                f"deploys {chart} from {own}/ in the same commit: both generate the same "
                "Application name, so ArgoCD keeps it. Its values still come from the default's "
                f"values files below {own}/values.yaml."
            )
            extra = f"deploy config on {ref.name}"
        if not plan.changes:
            raise ChangeRefusedError(
                f"nothing to change: {own}/ already holds this deploy config",
                details={"rule": "no-change"},
            )
        await self.validate(topology, plan)
        plan.reach = [ref]
        plan.title = mr_title(
            Repo.DAY2,
            Verb.OVERRIDE,
            ResourceType.ADDON,
            f"{team}/{chart}",
            f"{extra} (fleet default on {SCOPE_LABELS[scope]})",
        )
        self.confirm(plan, confirm_changes, expected_digest, dry_run=dry_run)
        return await self.finish(plan, user, message, dry_run=dry_run)

    async def _plan_own_deploy(
        self,
        plan: AuthoringPlan,
        destination: Destination,
        deploy: Mapping[str, object | None],
        last_commit_id: str | None,
    ) -> None:
        ref, chart = destination.ref, plan.chart
        unknown = sorted(set(deploy) - set(DEPLOY_OVERRIDE_KEYS))
        if unknown:
            raise ChangeRefusedError(
                f"{unknown[0]} is not a key a destination's own deploy config sets here",
                details={"rule": "key-not-editable"},
            )
        keys = {k: v for k, v in deploy.items() if v is not None and v != ""}
        if not keys:
            raise ChangeRefusedError(
                "an own deploy config needs at least one key (targetRevision, repourl, path or "
                "projectNamespace); send null to take the destination back into the default",
                details={"rule": "no-change"},
            )
        check_namespace(keys.get(PROJECT_NAMESPACE))
        app = PlannedApp(plan.team, ref, chart, AppSource.CLUSTER, destination.ocp_version)
        path = app.deploy_config_layers[-1].path
        inherited = await self.merged(plan, app.deploy_config_layers[:-1], after=False)
        repourl = keys.get(REPOURL) or inherited.get(REPOURL)
        if not truthy(repourl):
            raise ChangeRefusedError(
                f"no layer of {chart}'s deploy config sets a lowercase repourl; give one",
                details={"rule": str(Rule.REPOURL_MISSING), "chart": chart},
            )
        if {REPOURL, TARGET_REVISION, PATH} & set(keys):
            plan.findings += await self.check_chart_repo(
                str(repourl),
                keys.get(TARGET_REVISION, inherited.get(TARGET_REVISION)),
                keys.get(PATH, inherited.get(PATH)),
                file=str(path),
                where={"team": plan.team, "chart": chart, "cluster": ref.id},
            )
        if TARGET_REVISION in keys:
            plan.findings.append(
                warning(
                    Rule.EMERGENCY_PIN,
                    f"pins {chart} to {keys[TARGET_REVISION]} on {ref.name} only: it no longer "
                    "follows the team default or its OCP-version pins until the override goes",
                    team=plan.team,
                    cluster=ref.id,
                    chart=chart,
                )
            )
        tree = plan.state.repo.tree
        own = layout.chart_dir(ref, chart)
        others = [
            p
            for p in tree.files_under(own)
            if p.name not in (path.name, layout.VALUES_FILE) and not p.name.startswith(".")
        ]
        if others:
            raise ChangeRefusedError(
                f"{own}/ holds {others[0]} besides its values and deploy config; move or delete it "
                "by hand first",
                details={"rule": "adoption-blocked", "cluster": ref.id},
            )
        file = await self._sigs.read(plan.state.team, path) if tree.is_file(path) else None
        if file is None:
            await self.refuse_if_deleted(plan, path, last_commit_id)
            plan.changes.append(FileChange.create(path, dump_yaml(keys)))
            return
        doc, problem = parse_values(file.content, path=str(path))
        if problem is not None:
            raise ChangeRefusedError(
                f"{problem.message} ({path}): fix it by hand first",
                details={"rule": str(Rule.YAML_INVALID), "path": str(path)},
            )
        new = {k: v for k, v in doc.items() if k not in DEPLOY_OVERRIDE_KEYS or k in keys}
        new |= keys
        if not same_value(new, doc):
            self.write(
                plan,
                path,
                edit_mapping_text(file.content, new, path=str(path)),
                file,
                last_commit_id,
            )
