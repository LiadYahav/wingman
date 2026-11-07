"""Discovery, the catalog, installed charts and the values preview, against the seeded fake."""

from __future__ import annotations

import pytest

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.clusters import ClusterKind, ClusterRef
from wingman_day2.domain.errors import (
    AmbiguousClusterError,
    UnknownChartError,
    UnknownClusterError,
    UnknownTeamError,
)
from wingman_day2.domain.findings import Rule
from wingman_day2.domain.platform import AppSource

HERZI = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
PROD_MCE = "mce:site1:prod:ocp4-prod-mce-site1-a"
PREP_MCE = "mce:site1:prep:ocp4-prep-mce-site1-a"
DOK = "upi:site1:prod:ocp4-dok-site1"


async def commit(gitlab: InMemoryGitLab, project: str, files: dict[str, str]) -> None:
    pid = (await gitlab.get_project(project)).id
    await gitlab.commit(
        pid,
        branch="main",
        message="test setup",
        changes=[FileChange.create(RepoPath(p), c) for p, c in files.items()],
    )


# ── discovery ───────────────────────────────────────────────────────────────


async def test_clusters_come_from_team_folders_and_day1(services: Day2Services) -> None:
    topology = await services.topology.load()
    by_id = {s.ref.id: s for s in topology.clusters}
    assert by_id[HERZI].teams == ("redbull",) and by_id[HERZI].in_day1
    assert by_id[HERZI].ocp_version == "4.16.27"
    assert by_id[PROD_MCE].ocp_version == "4.16.27"
    assert by_id[PREP_MCE].ocp_version == "4.20.9"
    hawk = by_id["hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-hawk-site1"]
    assert hawk.teams == ("falcon", "orca")
    assert by_id[DOK].teams == ("falcon", "orca", "redbull") and not by_id[DOK].in_day1
    assert by_id["hub"].teams == ("falcon", "lynx", "redbull")


async def test_a_day1_cluster_no_team_places_gets_its_env_from_its_mce(
    services: Day2Services,
) -> None:
    topology = await services.topology.load()
    didush = topology.resolve("ocp4-prod-didush-site2-a")
    assert didush.ref == ClusterRef.hosted(
        "site2", "prod", "ocp4-prod-mce-site2-a", "ocp4-prod-didush-site2-a"
    )
    assert didush.teams == () and didush.in_day1


async def test_an_off_convention_day1_cluster_has_an_unknown_env_and_says_so(
    services: Day2Services,
) -> None:
    topology = await services.topology.load()
    demo = topology.resolve("ocp4-upgrade-demo")
    assert demo.ref.env == ""
    assert [f.rule for f in demo.findings] == [Rule.ENV_UNKNOWN]


async def test_resolve_takes_an_id_or_a_unique_bare_name(services: Day2Services) -> None:
    topology = await services.topology.load()
    assert topology.resolve(HERZI).ref.name == "ocp4-prod-herzi-site1"
    assert topology.resolve("ocp4-prod-herzi-site1", mce="ocp4-prod-mce-site1-a").ref.id == HERZI
    assert topology.resolve("hub").ref.kind is ClusterKind.HUB
    with pytest.raises(UnknownClusterError):
        topology.resolve("ocp4-prod-herzi-site1", mce="other-mce")
    with pytest.raises(UnknownClusterError):
        topology.resolve("hosted:site1:prod:ocp4-prod-mce-site1-a:nope")
    with pytest.raises(UnknownTeamError):
        topology.team("nope")


async def test_a_name_placed_twice_is_ambiguous_and_flagged(
    services: Day2Services, gitlab: InMemoryGitLab
) -> None:
    await commit(
        gitlab,
        "sigs/lynx",
        {"sites/site1/prep/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/x/values.yaml": "{}"},
    )
    topology = await services.topology.load()
    with pytest.raises(AmbiguousClusterError) as raised:
        topology.resolve("ocp4-prod-herzi-site1")
    candidates = raised.value.details["candidates"]
    assert isinstance(candidates, list) and HERZI in candidates
    assert Rule.CLUSTER_POSITION_CONFLICT in {f.rule for f in topology.findings}


# ── catalog ─────────────────────────────────────────────────────────────────


async def test_catalog_entries_carry_team_defaults_versions_and_placements(
    services: Day2Services,
) -> None:
    entries = {(e.team, e.chart): e for e in await services.catalog.entries()}
    roles = entries[("redbull", "cluster-roles")]
    assert roles.team_revision == "main" and roles.path == "."
    assert roles.versions == ("main", "2.1.5-hotfix", "2.0.0")
    assert roles.chart_project is not None
    assert entries[("falcon", "mce-agent")].fleet_defaults == ("mces",)
    kyverno = entries[("redbull", "kyverno")]
    assert kyverno.repo_url == "" and kyverno.versions is None
    assert {f.rule for f in kyverno.findings} == {Rule.REPOURL_MISCASED, Rule.REPOURL_MISSING}
    bmhgen = entries[("redbull", "bmhgen")]
    assert bmhgen.team_revision == "HEAD" and bmhgen.project_namespace == "metal3-system"
    assert bmhgen.sync_policy == {"syncOptions": ["CreateNamespace=true"]}


async def test_catalog_lookups(services: Day2Services, gitlab: InMemoryGitLab) -> None:
    await commit(
        gitlab,
        "sigs/redbull",
        {
            "operators/cluster-roles/ocp-versions/4.16.27/cluster-roles.yaml": (
                "targetRevision: 2.0.0\n"
            ),
            "operators/cluster-roles/ocp-versions/4.20.9/values.yaml": "a: 1\n",
            "operators/elsewhere/elsewhere.yaml": "repourl: https://example.invalid/x.git\n",
            "operators/broken/broken.yaml": "repourl: [\n",
        },
    )
    assert await services.catalog.versions("redbull", "kyverno") == []
    values = await services.catalog.default_values("redbull", "cluster-roles", "2.0.0")
    assert values.problem is None and "groups" in values.values
    missing = await services.catalog.default_values("redbull", "cluster-roles", "9.9.9")
    assert missing.problem is not None and "9.9.9" in missing.problem
    with pytest.raises(UnknownChartError):
        await services.catalog.entry("redbull", "nope")
    entry = await services.catalog.entry("redbull", "cluster-roles")
    assert [(p.version, p.target_revision) for p in entry.pins] == [
        ("4.16.27", "2.0.0"),
        ("4.20.9", None),
    ]
    elsewhere = await services.catalog.default_values("redbull", "elsewhere", "HEAD")
    assert elsewhere.problem is not None and "not a project on this GitLab" in elsewhere.problem
    assert (await services.catalog.entry("redbull", "elsewhere")).versions is None
    broken = await services.catalog.entry("redbull", "broken")
    assert Rule.YAML_INVALID in {f.rule for f in broken.findings}


# ── installed ───────────────────────────────────────────────────────────────


async def test_a_hosted_cluster_lists_its_own_chart_folders(services: Day2Services) -> None:
    charts = await services.installed.for_cluster("ocp4-prod-herzi-site1")
    assert [(c.app.team, c.app.chart, c.app.source) for c in charts.installed] == [
        ("redbull", "cluster-roles", AppSource.CLUSTER)
    ]
    roles = charts.installed[0]
    assert roles.deploy.leaf.name == "redbull-ocp4-prod-herzi-site1-cluster-roles-deploy"
    assert roles.deploy.leaf.target_revision == "main" and not roles.pinned
    assert roles.override.file is not None and roles.web_url.endswith(str(roles.app.folder))


async def test_an_mce_hub_gets_its_in_cluster_charts_plus_fleet_defaults(
    services: Day2Services,
) -> None:
    charts = await services.installed.for_cluster(PROD_MCE)
    assert sorted((c.app.team, c.app.chart, c.app.source) for c in charts.installed) == [
        ("falcon", "mce-agent", AppSource.FLEET_DEFAULT),
        ("redbull", "bmhgen", AppSource.CLUSTER),
        ("redbull", "dhcp-api-token", AppSource.FLEET_DEFAULT),
        ("redbull", "example-chart", AppSource.FLEET_DEFAULT),
        ("redbull", "kyverno", AppSource.CLUSTER),
    ]
    token = next(c for c in charts.installed if c.app.chart == "dhcp-api-token")
    assert (token.deploy.leaf.path, token.deploy.leaf.auto_sync) == ("charts/dhcp-api-token", True)
    assert str(token.override.layer.path) == (
        "defaults/mces/dhcp-api-token/values-ocp4-prod-mce-site1-a.yaml"
    )
    kyverno = next(c for c in charts.installed if c.app.chart == "kyverno")
    assert kyverno.deploy.leaf.repo_url == ""
    assert {f.rule for f in kyverno.findings} >= {Rule.REPOURL_MISCASED, Rule.REPOURL_MISSING}


async def test_an_exclusion_keeps_a_fleet_default_off_one_mce(services: Day2Services) -> None:
    charts = await services.installed.for_cluster(PREP_MCE)
    assert "dhcp-api-token" not in {c.app.chart for c in charts.installed}
    assert [(e.team, e.chart) for e in charts.excluded] == [("redbull", "dhcp-api-token")]


async def test_upi_and_hub_destinations(services: Day2Services) -> None:
    dok = await services.installed.for_cluster("ocp4-dok-site1", team="orca")
    assert sorted((c.app.chart, c.app.source, c.app.ocp_version) for c in dok.installed) == [
        ("cluster-roles", AppSource.CLUSTER, None),
        ("metrics", AppSource.FLEET_DEFAULT, None),
    ]
    falcon_dok = await services.installed.for_cluster(DOK, team="falcon")
    assert {c.app.ocp_version for c in falcon_dok.installed} == {"4.16.27"}
    hub = await services.installed.for_cluster("hub")
    assert sorted((c.app.team, c.app.chart) for c in hub.installed) == [
        ("falcon", "hub-reporter"),
        ("lynx", "backup"),
        ("redbull", "example-chart"),
    ]


async def test_a_pin_and_a_broken_values_file_show_up(
    services: Day2Services, gitlab: InMemoryGitLab
) -> None:
    pid = (await gitlab.get_project("sigs/redbull")).id
    folder = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/cluster-roles"
    await gitlab.commit(
        pid,
        branch="main",
        message="pin",
        changes=[
            FileChange.update(
                RepoPath(f"{folder}/cluster-roles.yaml"),
                "targetRevision: 2.0.0\n",
                last_commit_id=None,
            ),
            FileChange.update(RepoPath(f"{folder}/values.yaml"), "a: [\n", last_commit_id=None),
        ],
    )
    roles = (await services.installed.for_cluster(HERZI)).installed[0]
    assert roles.pinned and roles.deploy.leaf.target_revision == "2.0.0"
    assert {f.rule for f in roles.findings} == {Rule.EMERGENCY_PIN, Rule.YAML_INVALID}


# ── values preview ──────────────────────────────────────────────────────────


async def test_the_preview_merges_every_layer_with_provenance(
    services: Day2Services, gitlab: InMemoryGitLab
) -> None:
    folder = "sites/site1/prod/mces/ocp4-prod-mce-site1-a"
    await commit(
        gitlab,
        "sigs/redbull",
        {
            "operators/cluster-roles/ocp-versions/4.16.27/values.yaml": "pinned: true\n",
            "sites/site1/values.yaml": "site: site1\naggregateToView: false\n",
            f"{folder}/values.yaml": "mce: wide\n",
            f"{folder}/ocp4-prod-herzi-site1/values.yaml": "cluster: wide\n",
        },
    )
    preview = await services.preview.preview(HERZI, "redbull", "cluster-roles")
    assert preview.installed and preview.revision == "main"
    assert preview.merged.values == {
        "groups": {"admins": [], "viewers": []},
        "aggregateToView": False,
        "pinned": True,
        "site": "site1",
        "mce": "wide",
        "cluster": "wide",
    }
    assert preview.merged.provenance == {
        "groups": {"admins": "chart", "viewers": "chart"},
        "aggregateToView": "site",
        "pinned": "team-ocp-version",
        "site": "site",
        "mce": "mce",
        "cluster": "cluster-wide",
    }
    assert [x.exists for x in preview.layers] == [
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
    ]


async def test_the_preview_of_an_edit_and_of_another_version(services: Day2Services) -> None:
    edited = await services.preview.preview(
        HERZI, "redbull", "cluster-roles", override_values={"groups": {"admins": ["me"]}}
    )
    assert edited.merged.values["groups"] == {"admins": ["me"], "viewers": []}
    assert edited.merged.provenance["groups"] == {"admins": "cluster", "viewers": "chart"}
    old = await services.preview.preview(HERZI, "redbull", "cluster-roles", version="2.0.0")
    assert old.chart.revision == "2.0.0" and old.chart.problem is None


async def test_a_chart_not_yet_installed_previews_as_an_install(services: Day2Services) -> None:
    preview = await services.preview.preview(HERZI, "redbull", "bmhgen")
    assert not preview.installed and preview.app.source is AppSource.CLUSTER
    assert preview.deploy.leaf.target_revision == "HEAD"
    assert preview.chart.project is not None and preview.chart.problem is None
    with pytest.raises(UnknownChartError):
        await services.preview.preview(HERZI, "redbull", "nope")


async def test_a_preview_reports_unreadable_chart_defaults_instead_of_hiding_them(
    services: Day2Services,
) -> None:
    kyverno = await services.preview.preview(PROD_MCE, "redbull", "kyverno")
    assert kyverno.chart.problem is not None and "repourl" in kyverno.chart.problem
    token = await services.preview.preview(PROD_MCE, "redbull", "dhcp-api-token")
    assert token.chart.problem is not None and "charts/dhcp-api-token" in token.chart.problem
    upi = await services.preview.preview(DOK, "lynx", "backup")
    assert upi.app.ocp_version is None and upi.app.source is AppSource.CLUSTER
