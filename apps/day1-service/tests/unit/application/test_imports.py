"""Importing existing clusters into a flavor, on the seeded in-memory GitLab (ADR-0037)."""

from __future__ import annotations

from typing import Any

import pytest

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.drift import DriftState
from wingman_day1.application.imports import ImportPick, ImportStatus
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.cluster_file import read_provenance
from wingman_day1.domain.errors import InvalidInputError, ResourceNotFoundError, StaleError
from wingman_day1.domain.paths import ClusterRef

MCE = "ocp4-prod-mce-site1-a"
LARK = ClusterRef("site1", MCE, "ocp4-prod-lark-site1")
HERON = ClusterRef("site1", MCE, "ocp4-prod-heron-site1")
HERZI = ClusterRef("site1", MCE, "ocp4-prod-herzi-site1")
HEADER = '# specName: "agent-baseline"\n# specVersion: "1.0.0"\n'


async def main_file(gitlab: InMemoryGitLab, support: Any, ref: ClusterRef) -> Any:
    pid = await support.project_id(gitlab, support.DAY1)
    return await gitlab.read_file(pid, ref.path, "main")


async def picks(context: Day1Context, *refs: ClusterRef, relink: bool = False) -> list[ImportPick]:
    return [
        ImportPick(ref, (await context.clusters.get(ref)).last_commit_id, relink=relink)
        for ref in refs
    ]


async def put(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab, ref: ClusterRef, content: str
) -> None:
    await support.push(gitlab, support.DAY1, branch="main", file=str(ref.path), content=content)
    context.repos[RepoKey.DAY1].forget_files()


# ── Preview ──────────────────────────────────────────────────────────────────


async def test_the_preview_shows_each_clusters_drift_against_the_flavor(
    context: Day1Context,
) -> None:
    preview = await context.imports.preview("agent-baseline", [LARK, HERON])
    assert (preview.spec_name, preview.spec_version, preview.warnings) == (
        "agent-baseline",
        "1.0.0",
        (),
    )
    lark, heron = preview.candidates
    assert (lark.status, lark.problems) == (ImportStatus.READY, ())
    assert lark.drift.state is DriftState.DRIFTED
    assert [str(d.file_key) for d in lark.drift.value_drift] == [
        "nodepool[0].configs",
        "nodepool[1].configs",
    ]
    assert [(a.team, a.name) for a in lark.drift.addon_drift] == [("redbull", "cluster-roles")]
    assert [d.needs_decision is not None for d in heron.drift.value_drift] == [True, True]


async def test_a_flavor_that_locks_by_position_warns_about_imported_files(
    context: Day1Context,
) -> None:
    preview = await context.imports.preview("agent-dell", [LARK])
    assert preview.warnings == (
        "nodepools[0].configs locks one nodepool by position: on a cluster the flavor did not "
        "create it compares the file's nodepool[0], whichever that is; nodepools[*].configs "
        "compares every nodepool",
    )


async def test_the_preview_says_which_clusters_follow_a_flavor_already(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    lark = await main_file(gitlab, support, LARK)
    await put(context, support, gitlab, LARK, HEADER + lark.content)
    heron = await main_file(gitlab, support, HERON)
    await put(context, support, gitlab, HERON, '# specName: "agent-dell"\n' + heron.content)
    await put(context, support, gitlab, HERZI, "x: [\n")
    preview = await context.imports.preview("agent-baseline", [LARK, HERON, HERZI])
    linked, other, broken = preview.candidates
    assert linked.status is ImportStatus.LINKED
    assert linked.problems == (
        "ocp4-prod-lark-site1: already follows flavor agent-baseline v1.0.0; sync it instead",
    )
    assert other.status is ImportStatus.RELINK
    assert other.problems == (
        "ocp4-prod-heron-site1: follows flavor agent-dell v?; send relink: true to link it to "
        "agent-baseline instead",
    )
    assert broken.status is ImportStatus.REFUSED
    assert broken.problems[0].startswith(
        "ocp4-prod-herzi-site1: the cluster file does not parse, so Wingman cannot edit it"
    )
    assert broken.drift.state is DriftState.UNKNOWN


@pytest.mark.parametrize(
    ("refs", "problem"),
    [
        ([], "clusters: pick at least one cluster"),
        ([LARK, LARK], "clusters: ocp4-prod-lark-site1 is picked twice"),
        ([LARK] * 51, "clusters: 51 picked; one import takes at most 50"),
    ],
)
async def test_a_pick_that_cannot_be_one_import_is_refused(
    context: Day1Context, refs: list[ClusterRef], problem: str
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        await context.imports.preview("agent-baseline", refs)
    assert problem in caught.value.problems


async def test_an_unknown_flavor_or_cluster_is_not_found(context: Day1Context) -> None:
    with pytest.raises(ResourceNotFoundError):
        await context.imports.preview("nope", [LARK])
    with pytest.raises(ResourceNotFoundError):
        await context.imports.preview("agent-baseline", [ClusterRef("site1", MCE, "ocp4-nope")])


# ── Import ───────────────────────────────────────────────────────────────────


async def test_an_import_is_one_mr_that_adds_only_the_header_to_each_file(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    before = gitlab.snapshot(pid, "main")
    result = await context.imports.import_clusters(
        "agent-baseline",
        await picks(context, LARK, HERON),
        spec_version="1.0.0",
        user=support.ALICE,
    )
    mr = result.merge_request
    branch = gitlab.snapshot(pid, mr.source_branch)
    assert sorted(p for p in branch if branch[p] != before.get(p)) == sorted(
        [str(LARK.path), str(HERON.path)]
    )
    # Byte for byte: the header in front, the file (comments, vlanId, CI block) as it was.
    assert branch[str(LARK.path)] == HEADER + before[str(LARK.path)]
    assert branch[str(HERON.path)] == HEADER + before[str(HERON.path)]
    assert gitlab.snapshot(pid, "main") == before
    assert mr.title == "[Wingman/Day1] Import spec agent-baseline into 2 clusters"
    assert mr.description.startswith("Linking **2 clusters** to flavor `agent-baseline` v1.0.0.")
    assert (
        "- `ocp4-prod-lark-site1` (site1/ocp4-prod-mce-site1-a): 2 locked values differ, "
        "1 add-on missing"
    ) in mr.description
    assert (
        "- `ocp4-prod-heron-site1` (site1/ocp4-prod-mce-site1-a): 2 locked values differ, "
        "2 need a person to decide, 1 add-on missing"
    ) in mr.description


async def test_after_the_merge_the_imported_clusters_follow_the_flavor(
    context: Day1Context, support: Any
) -> None:
    result = await context.imports.import_clusters(
        "agent-baseline", await picks(context, LARK), spec_version="1.0.0", user=support.ALICE
    )
    mr = result.merge_request
    await context.approvals.approve(RepoKey.DAY1, mr.ref.iid, sha=mr.sha, approver=support.BOB)
    assert [d.ref for d in await context.drift.for_spec("agent-baseline")] == [LARK]
    assert (await context.drift.for_cluster(LARK)).state is DriftState.DRIFTED


async def test_a_cluster_on_another_flavor_is_refused_unless_relinked(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    lark = await main_file(gitlab, support, LARK)
    old_header = (
        '# specName: "agent-standard"\n# specVersion: "0.9.0"\n'
        '# wingmanAddons: [{"name": "cluster-roles", "override_values": {"a": 1}, '
        '"team": "redbull", "version": "main"}, {"name": "gone", "override_values": {"b": 2}, '
        '"team": "redbull", "version": "1"}]\n'
    )
    await put(context, support, gitlab, LARK, old_header + lark.content)
    with pytest.raises(InvalidInputError) as caught:
        await context.imports.import_clusters(
            "agent-baseline", await picks(context, LARK), spec_version="1.0.0", user=support.ALICE
        )
    assert caught.value.problems == (
        "ocp4-prod-lark-site1: follows flavor agent-standard v0.9.0; send relink: true to link "
        "it to agent-baseline instead",
    )
    result = await context.imports.import_clusters(
        "agent-baseline",
        await picks(context, LARK, relink=True),
        spec_version="1.0.0",
        user=support.ALICE,
    )
    pid = await support.project_id(gitlab, support.DAY1)
    relinked = gitlab.snapshot(pid, result.merge_request.source_branch)[str(LARK.path)]
    provenance = read_provenance(relinked)
    assert (provenance.spec_name, provenance.spec_version) == ("agent-baseline", "1.0.0")
    # The values asked for an add-on the new flavor also lists are kept; the rest go.
    assert provenance.requested_addons == (
        RequestedAddon("redbull", "cluster-roles", "main", {"a": 1}),
    )
    assert relinked.endswith(lark.content)
    assert "re-linked from flavor `agent-standard` v0.9.0" in result.merge_request.description


async def test_a_cluster_already_on_the_flavor_has_nothing_to_import(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    lark = await main_file(gitlab, support, LARK)
    await put(context, support, gitlab, LARK, HEADER + lark.content)
    with pytest.raises(InvalidInputError) as caught:
        await context.imports.import_clusters(
            "agent-baseline",
            await picks(context, LARK, relink=True),
            spec_version="1.0.0",
            user=support.ALICE,
        )
    assert caught.value.problems[0].endswith(
        "already follows flavor agent-baseline v1.0.0; sync it instead"
    )


async def test_a_file_that_moved_since_the_preview_fails_the_whole_import(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    chosen = await picks(context, LARK, HERON)
    heron = await main_file(gitlab, support, HERON)
    await put(context, support, gitlab, HERON, heron.content + "# a later edit\n")
    with pytest.raises(StaleError) as caught:
        await context.imports.import_clusters(
            "agent-baseline", chosen, spec_version="1.0.0", user=support.ALICE
        )
    assert str(caught.value).startswith("changed since the preview: ocp4-prod-heron-site1 (")
    assert await gitlab.list_merge_requests(pid, state=None) == []


async def test_an_import_after_other_files_changed_is_not_stale(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    # The preview's last_commit_id is the commit the repo was read at (ADR-0035);
    # a merge that touches only other files moves it, and the import still goes ahead.
    pid = await support.project_id(gitlab, support.DAY1)
    chosen = await picks(context, LARK)
    herzi = await main_file(gitlab, support, HERZI)
    await put(context, support, gitlab, HERZI, herzi.content + "# a later edit\n")
    assert (await context.clusters.get(LARK)).last_commit_id != chosen[0].last_commit_id
    result = await context.imports.import_clusters(
        "agent-baseline", chosen, spec_version="1.0.0", user=support.ALICE
    )
    branch = gitlab.snapshot(pid, result.merge_request.source_branch)
    assert branch[str(LARK.path)].startswith(HEADER)


async def test_a_flavor_that_moved_since_the_preview_fails_the_import(
    context: Day1Context, support: Any
) -> None:
    with pytest.raises(StaleError) as caught:
        await context.imports.import_clusters(
            "agent-baseline", await picks(context, LARK), spec_version="0.9.0", user=support.ALICE
        )
    assert str(caught.value) == (
        "flavor agent-baseline is now v1.0.0, not v0.9.0; preview the import again"
    )


async def test_an_unparsable_file_is_refused_and_nothing_is_opened(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    await put(context, support, gitlab, HERZI, "x: [\n")
    with pytest.raises(InvalidInputError) as caught:
        await context.imports.import_clusters(
            "agent-baseline",
            await picks(context, LARK, HERZI),
            spec_version="1.0.0",
            user=support.ALICE,
        )
    (problem,) = caught.value.problems
    assert problem.startswith("ocp4-prod-herzi-site1: the cluster file does not parse")
    assert await gitlab.list_merge_requests(pid, state=None) == []
