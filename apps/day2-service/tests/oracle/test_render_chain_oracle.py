"""The oracle: Wingman's platform simulation against the team's own, ``render_chain.py``.

``render_chain.py`` (vendored next to this file, with the five platform charts
of ``argocd-day2-platform`` @ 979e306) renders the real ApplicationSet chain
with ``helm template``. For the same repo trees, Wingman's discovery
(``TopologyService`` over the in-memory GitLab, exactly as the service reads
GitLab) must produce:

- the same leaf Applications, on the same Argo instances;
- for each, the same workload value-file list in the same order, and the same
  subset of them that exists;
- the same deploy-config value-file list for its wrapper app;
- the same identity fields (repoURL, targetRevision, path, releaseName,
  destination, namespace, syncPolicy) and OCP-version label;
- the same render_chain rules failing, for trees that break them.

Needs ``helm`` on PATH; skipped locally without it, and a failure in CI (where
``CI`` is set) rather than a silent skip.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.infrastructure.snapshots import RepoSnapshots
from wingman_core.testing.fixtures import default_fixture_root, load_fixture_projects
from wingman_day2.application.apps import load_deploy
from wingman_day2.application.authoring import AuthoringResult, NewAddon
from wingman_day2.application.services import Day2Services
from wingman_day2.application.topology import Topology, TopologyService
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.findings import Rule, Severity
from wingman_day2.domain.sync_policy import SyncSettings
from wingman_day2.infrastructure.repositories import (
    GitLabChartRepository,
    GitLabDay1Repository,
    GitLabSigsRepository,
)

HERE = Path(__file__).parent
PLATFORM = HERE / "platform"
URL = "https://gitlab.example.invalid"
TEAMS = ("falcon", "lynx", "orca", "redbull")
DAY1 = "gitops-day1/platform-config"

if shutil.which("helm") is None:
    if os.environ.get("CI"):
        raise RuntimeError("the render_chain oracle needs helm on PATH in CI")
    pytest.skip("helm is not installed", allow_module_level=True)

Files = dict[str, dict[str, str]]


def _render_chain() -> ModuleType:
    spec = importlib.util.spec_from_file_location("day2_render_chain", HERE / "render_chain.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RC = _render_chain()

# The rules render_chain.py itself fails a snapshot on; Wingman's own lints are not here.
RENDER_CHAIN_RULES = frozenset(
    {
        Rule.ENV_NOT_ALLOWED,
        Rule.DAY1_VERSION_MISSING,
        Rule.MASTERTAG_MISSING,
        Rule.MASTERTAG_INVALID,
        Rule.UPI_NAME_IN_CLUSTER,
        Rule.UPI_NAME_REUSED,
        Rule.UPI_VERSION_FILE_INVALID,
        Rule.LEGACY_LAYOUT,
        Rule.EXCLUSIONS_HUB,
        Rule.EXCLUSIONS_SCHEMA,
        Rule.EXCLUSIONS_UNKNOWN_CHART,
        Rule.EXCLUSIONS_UNKNOWN_TARGET,
        Rule.DUPLICATE_APP,
    }
)


def fixture_files() -> Files:
    return {
        p.path_with_namespace: dict(p.files)
        for p in load_fixture_projects(default_fixture_root(), substitutions={"GITLAB_URL": URL})
    }


def write_tree(files: Files, root: Path) -> None:
    for project, tree in files.items():
        for path, content in tree.items():
            target = root / project / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")


async def wingman(files: Files) -> tuple[Topology, GitLabSigsRepository]:
    gitlab = InMemoryGitLab(base_url=URL)
    for project, tree in files.items():
        gitlab.create_project(project, tree)
    cache = TtlCache()
    snapshots = RepoSnapshots(gitlab, cache, ttl=60)
    sigs = GitLabSigsRepository(gitlab, cache, snapshots, group="sigs", branch="main", ttl=60)
    day1 = GitLabDay1Repository(gitlab, cache, snapshots, project=DAY1, branch="main", ttl=60)
    return await TopologyService(sigs, day1).load(), sigs


def oracle(files: Files, root: Path, team: str) -> dict[str, Any]:
    """render_chain's snapshot of ``team`` (JSON-shaped data from the vendored module)."""
    write_tree(files, root)
    return RC.snapshot(sigs=root / "sigs" / team, platform=PLATFORM, day1=root / DAY1, group=team)


def _leaves(apps: Mapping[str, dict]) -> dict[str, dict]:
    return {
        uid: app
        for uid, app in apps.items()
        if app["identity"]["releaseName"] is not None
        and RC.PLATFORM_MARKER not in (app["identity"]["source_repoURL"] or "")
    }


_RULES: tuple[tuple[str, Rule | None], ...] = (
    ("DUPLICATE app generated", Rule.DUPLICATE_APP),
    ("env folder", Rule.ENV_NOT_ALLOWED),
    ("no day1 version file", Rule.DAY1_VERSION_MISSING),
    ("no top-level mastertag", Rule.MASTERTAG_MISSING),
    ("is not <major>", Rule.MASTERTAG_INVALID),
    ("cannot be named in-cluster", Rule.UPI_NAME_IN_CLUSTER),
    ("reuses an MCE or hosted-cluster name", Rule.UPI_NAME_REUSED),
    ("a UPI version file carries", Rule.UPI_VERSION_FILE_INVALID),
    ("Rule 3", Rule.EXCLUSIONS_HUB),
    ("Rule 0", Rule.EXCLUSIONS_SCHEMA),
    ("Rule 1", Rule.EXCLUSIONS_UNKNOWN_CHART),
    ("Rule 2", Rule.EXCLUSIONS_UNKNOWN_TARGET),
    ("legacy mces/ layout", Rule.LEGACY_LAYOUT),
    ("render aborted", None),
)


def oracle_rules(failures: list[str]) -> set[Rule]:
    rules: set[Rule] = set()
    for message in failures:
        matched = [rule for needle, rule in _RULES if needle in message]
        assert matched, f"unclassified render_chain failure: {message}"
        if matched[0] is not None:
            rules.add(matched[0])
    return rules


async def assert_same_apps(files: Files, root: Path, team: str) -> None:
    snapshot = oracle(files, root, team)
    topology, sigs = await wingman(files)
    state = topology.team(team)
    expected = _leaves(snapshot["apps"])
    mine = {}
    for app in state.plan.apps:
        deploy = await load_deploy(sigs, state.team, state.repo.tree, app)
        mine[f"{deploy.leaf.argo}:{deploy.leaf.name}"] = (app, deploy)
    assert expected, "the oracle rendered no leaf at all"
    assert sorted(mine) == sorted(expected)
    for uid, (app, deploy) in mine.items():
        leaf, rc_leaf = deploy.leaf, expected[uid]
        tree = state.repo.tree
        assert rc_leaf["valueFiles"] == [f"$values/{x.path}" for x in app.workload_layers], uid
        assert [r["path"] for r in rc_leaf["resolved"]] == [
            str(x.path) for x in app.workload_layers if tree.is_file(x.path)
        ], uid
        wrapper = snapshot["apps"][f"{leaf.argo}:{app.generator_app}"]
        assert wrapper["valueFiles"] == [f"$values/{x.path}" for x in app.deploy_config_layers]
        assert [r["path"] for r in wrapper["resolved"]] == [
            str(x.layer.path) for x in deploy.layers if x.exists
        ]
        destination = {"name": leaf.destination}
        if leaf.destination_namespace:
            destination["namespace"] = leaf.destination_namespace
        assert rc_leaf["identity"] == {
            "name": leaf.name,
            "namespace": leaf.namespace,
            "project": team,
            "destination": destination,
            "source_repoURL": leaf.repo_url,
            "source_targetRevision": leaf.target_revision,
            "source_path": leaf.path,
            "releaseName": leaf.release_name,
            "syncPolicy": leaf.sync_policy,
            "ignoreDifferences": leaf.ignore_differences,
        }, uid
        assert rc_leaf["labels"].get("day2.gitops/ocp-version") == app.ocp_version, uid


@pytest.mark.parametrize("team", TEAMS)
async def test_every_fixture_team_renders_the_same_apps(team: str, tmp_path: Path) -> None:
    files = fixture_files()
    await assert_same_apps(files, tmp_path, team)
    snapshot = oracle(files, tmp_path, team)
    topology, _ = await wingman(files)
    assert snapshot["check_failures"] == []
    assert [f for f in topology.team(team).findings if f.severity is Severity.ERROR] == []


def _add(project: str, path: str, content: str) -> Callable[[Files], None]:
    def mutate(files: Files) -> None:
        files[project][path] = content

    return mutate


def _remove(project: str, path: str) -> Callable[[Files], None]:
    def mutate(files: Files) -> None:
        del files[project][path]

    return mutate


def _all(*mutations: Callable[[Files], None]) -> Callable[[Files], None]:
    def mutate(files: Files) -> None:
        for m in mutations:
            m(files)

    return mutate


RB = "sigs/redbull"
HOSTED_DEFAULT = _add(RB, "defaults/hosted-clusters/cluster-roles/values.yaml", "fleet: true\n")
EXCLUDE_ALL = _add(
    RB,
    "defaults/hosted-clusters/exclusions.yaml",
    "exclusions:\n  cluster-roles: [ocp4-prep-eyal-site1, ocp4-prep-itay-site1, "
    "ocp4-prod-herzi-site1, ocp4-prod-karniol-site1]\n",
)
MCE_EXCLUSIONS = "defaults/mces/exclusions.yaml"

SCENARIOS: dict[str, tuple[str, Callable[[Files], None], set[Rule], bool]] = {
    # name: (team, mutation, rules both must report, whether the render completes)
    "xor: a fleet default also in cluster folders": (
        "redbull",
        HOSTED_DEFAULT,
        {Rule.DUPLICATE_APP},
        True,
    ),
    "xor: excluded clusters may keep their own folder": (
        "redbull",
        _all(HOSTED_DEFAULT, EXCLUDE_ALL),
        set(),
        True,
    ),
    "exclusions rule 0: a stray top-level key": (
        "redbull",
        _add(
            RB,
            MCE_EXCLUSIONS,
            "mastertag: 4.1.1\nexclusions:\n  dhcp-api-token: [ocp4-prep-mce-site1-a]\n",
        ),
        {Rule.EXCLUSIONS_SCHEMA},
        True,
    ),
    "exclusions rule 1: an unknown chart": (
        "redbull",
        _add(
            RB,
            MCE_EXCLUSIONS,
            "exclusions:\n  dhcp-api-token: [ocp4-prep-mce-site1-a]\n"
            "  ghost: [ocp4-prep-mce-site1-a]\n",
        ),
        {Rule.EXCLUSIONS_UNKNOWN_CHART},
        True,
    ),
    "exclusions rule 2: an unknown MCE": (
        "redbull",
        _add(RB, MCE_EXCLUSIONS, "exclusions:\n  dhcp-api-token: [ocp4-nope]\n"),
        {Rule.EXCLUSIONS_UNKNOWN_TARGET},
        True,
    ),
    "exclusions rule 3: a hub exclusions file": (
        "redbull",
        _add(RB, "defaults/hub/exclusions.yaml", "exclusions: {}\n"),
        {Rule.EXCLUSIONS_HUB},
        True,
    ),
    "env outside prod/prep/test": (
        "redbull",
        _add(
            RB,
            "sites/site2/staging/mces/ocp4-prod-mce-site2-a/ocp4-prod-didush-site2-a/cluster-roles/values.yaml",
            "{}\n",
        ),
        {Rule.ENV_NOT_ALLOWED},
        True,
    ),
    "a hosted-cluster folder day1 does not know": (
        "redbull",
        _add(
            RB,
            "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ghost/cluster-roles/values.yaml",
            "{}\n",
        ),
        {Rule.DAY1_VERSION_MISSING},
        False,
    ),
    "an MCE without its day1 version.yaml": (
        "redbull",
        _remove(DAY1, "sites/site1/mces/ocp4-prep-mce-site1-a/version.yaml"),
        {Rule.DAY1_VERSION_MISSING},
        False,
    ),
    "a day1 mastertag without a patch version": (
        "redbull",
        _add(
            DAY1,
            "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-herzi-site1.yaml",
            "mastertag: '4.16'\n",
        ),
        {Rule.MASTERTAG_INVALID},
        True,
    ),
    "a UPI folder reusing a hosted-cluster name": (
        "redbull",
        _add(RB, "sites/site1/prod/upi/ocp4-prod-herzi-site1/cluster-roles/values.yaml", "{}\n"),
        {Rule.UPI_NAME_REUSED},
        True,
    ),
    "a UPI version file with another key": (
        "falcon",
        _add(
            "sigs/falcon",
            "sites/site1/prod/upi/ocp4-dok-site1/version.yaml",
            "mastertag: 4.16.27-x86_64\nreplicas: 2\n",
        ),
        {Rule.UPI_VERSION_FILE_INVALID},
        True,
    ),
    "a UPI folder named in-cluster": (
        "orca",
        _add("sigs/orca", "sites/site1/prod/upi/in-cluster/metrics/values.yaml", "{}\n"),
        {Rule.UPI_NAME_IN_CLUSTER},
        False,
    ),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
async def test_broken_trees_fail_the_same_rules(name: str, tmp_path: Path) -> None:
    team, mutate, rules, renders = SCENARIOS[name]
    files = fixture_files()
    mutate(files)
    snapshot = oracle(files, tmp_path, team)
    topology, _ = await wingman(files)
    mine = {
        f.rule
        for f in topology.team(team).findings
        if f.severity is Severity.ERROR and f.rule in RENDER_CHAIN_RULES
    }
    assert oracle_rules(snapshot["check_failures"]) == mine == rules
    if renders:
        await assert_same_apps(files, tmp_path / "again", team)


# ── Authoring (ADR-0043): what Wingman writes renders as it says ────────────


async def authored(
    files: Files, act: Callable[[Day2Services], Awaitable[AuthoringResult]]
) -> Files:
    """``files`` after the MR ``act`` opens on Wingman over them (its branch, as merged)."""
    gitlab = InMemoryGitLab(base_url=URL)
    for project, tree in files.items():
        gitlab.create_project(project, tree)
    cache = TtlCache()
    snapshots = RepoSnapshots(gitlab, cache, ttl=60)
    services = Day2Services.build(
        gitlab=gitlab,
        sigs=GitLabSigsRepository(gitlab, cache, snapshots, group="sigs", branch="main", ttl=60),
        day1=GitLabDay1Repository(gitlab, cache, snapshots, project=DAY1, branch="main", ttl=60),
        charts=GitLabChartRepository(gitlab, cache, base_url=URL, ttl=60),
        clock=lambda: datetime(2026, 11, 12, tzinfo=UTC),
        gitlab_url=URL,
    )
    result = await act(services)
    assert result.merge_request is not None
    project = await gitlab.get_project(f"sigs/{result.plan.team}")
    after = {name: dict(tree) for name, tree in files.items()}
    after[project.path_with_namespace] = gitlab.snapshot(
        project.id, result.merge_request.source_branch
    )
    return after


def workload(files: Files, team: str, leaf: dict[str, Any]) -> dict[str, Any]:
    """The workload values a leaf's existing value files merge to (the chart's own aside)."""
    merged: dict[str, Any] = {}
    for entry in leaf["resolved"]:
        assert entry["repo"] == "sigs", entry
        merged = RC.deep_merge(merged, yaml.safe_load(files[f"sigs/{team}"][entry["path"]]) or {})
    return merged


async def test_a_made_default_keeps_every_app_its_identity_and_its_values(tmp_path: Path) -> None:
    files = fixture_files()
    before = _leaves(oracle(files, tmp_path / "before", "redbull")["apps"])
    after_files = await authored(
        files,
        lambda day2: day2.authoring.make_default(
            "redbull",
            "cluster-roles",
            DefaultsScope.HOSTED_CLUSTERS,
            User("jane", Role.ADMIN),
            values={},
        ),
    )
    snapshot = oracle(after_files, tmp_path / "after", "redbull")
    assert snapshot["check_failures"] == []
    after = _leaves(snapshot["apps"])
    # The same leaf apps exist, with the same identity and the same values: ArgoCD keeps them.
    assert sorted(after) == sorted(before)
    for uid, leaf in after.items():
        assert leaf["identity"] == before[uid]["identity"], uid
        assert workload(after_files, "redbull", leaf) == workload(files, "redbull", before[uid]), (
            uid
        )
    moved = [uid for uid in after if "cluster-roles" in uid and "upi" not in uid]
    assert len(moved) == 4
    assert all(
        any(r["path"].startswith("defaults/hosted-clusters/") for r in after[uid]["resolved"])
        or not after[uid]["resolved"]
        for uid in moved
    )
    await assert_same_apps(after_files, tmp_path / "again", "redbull")


async def test_a_created_addon_and_its_default_render_as_wingman_says(tmp_path: Path) -> None:
    files = fixture_files()
    spec = NewAddon(
        team="redbull",
        chart="podinfo",
        repourl=f"{URL}/helm-charts/example-chart.git",
        sync=SyncSettings(True, False, True, ("CreateNamespace=true", "ServerSideApply=true")),
        project_namespace="podinfo",
        values={"replicas": 2},
        default_scope=DefaultsScope.MCES,
        default_values={"fleet": True},
    )
    after_files = await authored(
        files, lambda day2: day2.authoring.create(spec, User("jane", Role.ADMIN))
    )
    snapshot = oracle(after_files, tmp_path, "redbull")
    assert snapshot["check_failures"] == []
    podinfo = {uid: leaf for uid, leaf in _leaves(snapshot["apps"]).items() if "podinfo" in uid}
    assert sorted(podinfo) == [
        "ocp4-prep-mce-site1-a:redbull-in-cluster-podinfo-deploy",
        "ocp4-prod-mce-site1-a:redbull-in-cluster-podinfo-deploy",
    ]
    for leaf in podinfo.values():
        assert leaf["identity"]["syncPolicy"] == {
            "automated": {"prune": False, "selfHeal": True},
            "syncOptions": ["CreateNamespace=true", "ServerSideApply=true"],
        }
        assert leaf["identity"]["source_repoURL"] == f"{URL}/helm-charts/example-chart.git"
        assert leaf["identity"]["destination"] == {"name": "in-cluster", "namespace": "podinfo"}
        assert workload(after_files, "redbull", leaf) == {"replicas": 2, "fleet": True}
    await assert_same_apps(after_files, tmp_path / "again", "redbull")


# ── Operators (ADR-0053): exclusions and per-destination overrides render as said ──

ADMIN = User("jane", Role.ADMIN)
PROD_MCE = "mce:site1:prod:ocp4-prod-mce-site1-a"
PREP_MCE = "mce:site1:prep:ocp4-prep-mce-site1-a"
HERZI = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"


def confirming(
    write: Callable[..., Awaitable[AuthoringResult]],
) -> Callable[[Day2Services], Awaitable[AuthoringResult]]:
    """An ``authored`` act: preview the write, then open it confirming what the preview showed."""

    async def act(day2: Day2Services) -> AuthoringResult:
        del day2
        preview = await write(dry_run=True)
        return await write(
            confirm_changes=preview.plan.needs_confirmation, expected_digest=preview.plan.digest
        )

    return act


async def authored_with(
    files: Files, make: Callable[[Day2Services], Callable[..., Awaitable[AuthoringResult]]]
) -> tuple[Files, AuthoringResult]:
    """``files`` after the confirmed MR of ``make(day2)``, and its result."""
    seen: list[AuthoringResult] = []

    async def act(day2: Day2Services) -> AuthoringResult:
        result = await confirming(make(day2))(day2)
        seen.append(result)
        return result

    after = await authored(files, act)
    return after, seen[0]


async def test_an_excluded_mce_loses_its_app_and_nothing_else_moves(tmp_path: Path) -> None:
    files = fixture_files()
    before = _leaves(oracle(files, tmp_path / "before", "redbull")["apps"])
    after_files, result = await authored_with(
        files,
        lambda day2: lambda **kw: day2.fleet_targets.set_exclusions(
            "redbull", "dhcp-api-token", DefaultsScope.MCES, [PREP_MCE, PROD_MCE], ADMIN, **kw
        ),
    )
    snapshot = oracle(after_files, tmp_path / "after", "redbull")
    assert snapshot["check_failures"] == []
    after = _leaves(snapshot["apps"])
    gone = "ocp4-prod-mce-site1-a:redbull-in-cluster-dhcp-api-token-deploy"
    assert sorted(set(before) - set(after)) == [gone] and set(after) <= set(before)
    # Wingman said exactly that: one app removed, its workload orphaned.
    assert [(i.ref.id, i.app_name, i.orphaned) for i in result.plan.impact] == [
        (PROD_MCE, "redbull-in-cluster-dhcp-api-token-deploy", True)
    ]
    for uid, leaf in after.items():
        assert leaf["identity"] == before[uid]["identity"], uid
    await assert_same_apps(after_files, tmp_path / "again", "redbull")


async def test_an_included_mce_gets_its_app_back(tmp_path: Path) -> None:
    files = fixture_files()
    before = _leaves(oracle(files, tmp_path / "before", "redbull")["apps"])
    after_files, result = await authored_with(
        files,
        lambda day2: lambda **kw: day2.fleet_targets.set_exclusions(
            "redbull", "dhcp-api-token", DefaultsScope.MCES, [], ADMIN, **kw
        ),
    )
    snapshot = oracle(after_files, tmp_path / "after", "redbull")
    assert snapshot["check_failures"] == []
    after = _leaves(snapshot["apps"])
    back = "ocp4-prep-mce-site1-a:redbull-in-cluster-dhcp-api-token-deploy"
    assert sorted(set(after) - set(before)) == [back] and set(before) <= set(after)
    assert [(i.ref.id, str(i.effect)) for i in result.plan.impact] == [(PREP_MCE, "added")]
    await assert_same_apps(after_files, tmp_path / "again", "redbull")


async def test_a_value_override_changes_that_destinations_values_only(tmp_path: Path) -> None:
    files = fixture_files()
    before = _leaves(oracle(files, tmp_path / "before", "redbull")["apps"])
    after_files, _ = await authored_with(
        files,
        lambda day2: lambda **kw: day2.fleet_targets.set_destination_values(
            "redbull", "example-chart", DefaultsScope.MCES, PROD_MCE, {"replicas": 7}, ADMIN, **kw
        ),
    )
    snapshot = oracle(after_files, tmp_path / "after", "redbull")
    assert snapshot["check_failures"] == []
    after = _leaves(snapshot["apps"])
    assert sorted(after) == sorted(before)
    target = "ocp4-prod-mce-site1-a:redbull-in-cluster-example-chart-deploy"
    for uid, leaf in after.items():
        assert leaf["identity"] == before[uid]["identity"], uid
        mine, theirs = (
            workload(after_files, "redbull", leaf),
            workload(files, "redbull", before[uid]),
        )
        if uid == target:
            assert mine == {**theirs, "replicas": 7}
        else:
            assert mine == theirs, uid
    await assert_same_apps(after_files, tmp_path / "again", "redbull")


async def test_an_own_deploy_config_keeps_the_app_and_pins_that_destination_only(
    tmp_path: Path,
) -> None:
    files = fixture_files()
    before = _leaves(oracle(files, tmp_path / "before", "redbull")["apps"])
    after_files, _ = await authored_with(
        files,
        lambda day2: lambda **kw: day2.fleet_targets.set_destination_deploy(
            "redbull",
            "example-chart",
            DefaultsScope.MCES,
            PROD_MCE,
            {"targetRevision": "HEAD"},
            ADMIN,
            **kw,
        ),
    )
    snapshot = oracle(after_files, tmp_path / "after", "redbull")
    # The platform's carve-out: the exclusion and the own folder together are no duplicate.
    assert snapshot["check_failures"] == []
    after = _leaves(snapshot["apps"])
    assert sorted(after) == sorted(before)
    target = "ocp4-prod-mce-site1-a:redbull-in-cluster-example-chart-deploy"
    for uid, leaf in after.items():
        expected = dict(before[uid]["identity"])
        if uid == target:
            expected["source_targetRevision"] = "HEAD"
        assert leaf["identity"] == expected, uid
        assert workload(after_files, "redbull", leaf) == workload(files, "redbull", before[uid])
    await assert_same_apps(after_files, tmp_path / "again", "redbull")


async def test_a_stale_exclusion_does_not_delete_an_adopted_clusters_app(tmp_path: Path) -> None:
    # Review of 3.8.0: with the entry left in place, herzi's app vanished after the move.
    files = fixture_files()
    files[RB]["defaults/hosted-clusters/exclusions.yaml"] = (
        "exclusions:\n  cluster-roles:\n    - ocp4-prod-herzi-site1\n"
    )
    before = _leaves(oracle(files, tmp_path / "before", "redbull")["apps"])
    after_files, result = await authored_with(
        files,
        lambda day2: lambda **kw: day2.authoring.make_default(
            "redbull", "cluster-roles", DefaultsScope.HOSTED_CLUSTERS, ADMIN, values={}, **kw
        ),
    )
    assert result.plan.needs_confirmation == [HERZI]
    snapshot = oracle(after_files, tmp_path / "after", "redbull")
    assert snapshot["check_failures"] == []
    after = _leaves(snapshot["apps"])
    assert sorted(after) == sorted(before)
    for uid, leaf in after.items():
        assert leaf["identity"] == before[uid]["identity"], uid
    await assert_same_apps(after_files, tmp_path / "again", "redbull")


async def test_a_create_changes_existing_folders_exactly_as_wingman_lists(tmp_path: Path) -> None:
    # Review of 3.8.0: a new team layer under a cluster's own podinfo/ changes what it deploys.
    files = fixture_files()
    folder = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/podinfo"
    files[RB][f"{folder}/podinfo.yaml"] = f"repourl: {URL}/helm-charts/example-chart.git\n"
    files[RB][f"{folder}/values.yaml"] = "replicas: 1\n"
    before = _leaves(oracle(files, tmp_path / "before", "redbull")["apps"])
    spec = NewAddon(
        team="redbull",
        chart="podinfo",
        repourl=f"{URL}/helm-charts/example-chart.git",
        sync=SyncSettings(True, True, True, ("CreateNamespace=true",)),
        project_namespace="other-ns",
        values={"resources": {"limits": {"cpu": "1"}}},
    )

    def make(day2: Day2Services) -> Callable[..., Awaitable[AuthoringResult]]:
        async def write(**kw: Any) -> AuthoringResult:
            confirm = tuple(kw.pop("confirm_changes", ()))
            return await day2.authoring.create(replace(spec, confirm_changes=confirm), ADMIN, **kw)

        return write

    after_files, result = await authored_with(files, make)
    (impact,) = result.plan.impact
    assert impact.ref.id == HERZI
    uid = "ocp4-prod-mce-site1-a:redbull-ocp4-prod-herzi-site1-podinfo-deploy"
    after = _leaves(oracle(after_files, tmp_path / "after", "redbull")["apps"])
    # What the render changes for herzi is what Wingman listed: namespace, sync, values.
    assert before[uid]["identity"]["destination"] == {"name": "ocp4-prod-herzi-site1"}
    assert after[uid]["identity"]["destination"] == {
        "name": "ocp4-prod-herzi-site1",
        "namespace": "other-ns",
    }
    assert after[uid]["identity"]["syncPolicy"] == {
        "automated": {"prune": True, "selfHeal": True},
        "syncOptions": ["CreateNamespace=true"],
    }
    assert workload(after_files, "redbull", after[uid]) == {
        "replicas": 1,
        "resources": {"limits": {"cpu": "1"}},
    }
    assert {c.key for c in impact.changes} == {
        "projectNamespace",
        "syncPolicy.automated.prune",
        "syncPolicy.automated.selfHeal",
        "syncPolicy.syncOptions",
        "resources.limits.cpu",
    }
