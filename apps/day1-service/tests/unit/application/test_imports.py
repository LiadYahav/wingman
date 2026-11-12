"""Importing existing clusters into a flavor on the seeded in-memory GitLab (ADR-0037, 0044)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

import pytest

from wingman_core.domain.errors import (
    AmbiguousWriteError,
    GitUnavailableError,
    RevisionConflictError,
)
from wingman_core.domain.mr_conventions import Repo
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application import imports
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.drift import DriftState
from wingman_day1.application.imports import ImportPick, ImportService, ImportStatus
from wingman_day1.domain.addons import RequestedAddon
from wingman_day1.domain.changes import ClusterChange, ProvisionResult
from wingman_day1.domain.cluster_file import read_provenance
from wingman_day1.domain.errors import InvalidInputError, ResourceNotFoundError, StaleError
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.merge_requests import GitClusterProvisioner, MergeRequestWriter
from wingman_day1.infrastructure.repositories import CachedRepository
from wingman_day1.ports import ClusterProvisioner

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


async def test_an_import_opens_one_mr_per_cluster_each_adding_only_its_header(
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
    assert (result.spec_name, result.spec_version, result.failed) == ("agent-baseline", "1.0.0", ())
    assert [o.cluster for o in result.opened] == [LARK, HERON]
    for opened in result.opened:
        mr, ref = opened.merge_request, opened.cluster
        branch = gitlab.snapshot(pid, mr.source_branch)
        # Each MR changes its own file only: byte for byte, the header in front, the
        # file (comments, vlanId, CI block) as it was.
        assert [p for p in branch if branch[p] != before.get(p)] == [str(ref.path)]
        assert branch[str(ref.path)] == HEADER + before[str(ref.path)]
        assert (
            mr.title == f"[Wingman/Day1] Import cluster {ref.name} into spec agent-baseline v1.0.0"
        )
    assert gitlab.snapshot(pid, "main") == before
    assert len(await gitlab.list_merge_requests(pid, state=None)) == 2
    lark, heron = (o.merge_request.description for o in result.opened)
    assert lark.startswith(
        "Linking hosted cluster **ocp4-prod-lark-site1** to flavor `agent-baseline` v1.0.0.\n\n"
        "Site `site1`, MCE `ocp4-prod-mce-site1-a`."
    )
    # Each description shows its own cluster's drift, not the other's
    assert "Once linked: 2 locked values differ, 1 add-on missing." in lark
    assert "- add-on `redbull/cluster-roles`: missing; day2 installs it" in lark
    assert "ocp4-prod-heron-site1" not in lark
    assert "Once linked: 2 locked values differ, 2 need a person to decide, 1 add-on missing." in (
        heron
    )
    assert "ocp4-prod-lark-site1" not in heron


async def test_an_import_mr_lists_each_drifted_value_and_says_when_add_ons_are_unknown(
    context: Day1Context, support: Any, day2: FakeDay2Addons
) -> None:
    day2.unavailable = True
    result = await context.imports.import_clusters(
        "agent-baseline", await picks(context, LARK), spec_version="1.0.0", user=support.ALICE
    )
    lines = result.opened[0].merge_request.description.split("\n---\n")[0].splitlines()
    assert lines[
        lines.index("Once linked: 2 locked values differ, missing add-ons unknown.") :
    ] == [
        "Once linked: 2 locked values differ, missing add-ons unknown.",
        "- `nodepool[0].configs` (nodepool `prod-lark-site1-dell-r660-site1-128c-1024gb-5tb`): "
        "a sync removes `worker-kubeletconfig-reserved`",
        "- `nodepool[1].configs` (nodepool `prod-lark-site1-dell-r760-site1-64c-512gb-20tb`): "
        "a sync adds `nic-ring-buffer`; removes `restored-example-config`",
        "- add-ons: day2 did not answer, so missing add-ons are unknown: day2 unreachable listing "
        "addons of ocp4-prod-lark-site1 (fake)",
    ]


OWNED = """apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: agent-owned
  description: "One team's clusters: its owner number and the first nodepool's size are fixed"
  version: "1.0.0"
spec:
  day1:
    structure:
      nodepools:
        - {}
    locked_paths:
      - owner_anaf
      - nodepools[0].replicas
    values:
      owner_anaf: "99"
      nodepools:
        - replicas: 4
  day2:
    addons: []
"""


async def test_an_import_mr_shows_a_locked_value_as_the_file_has_it_and_the_flavor_locks_it(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/agent-owned.yaml", content=OWNED
    )
    context.repos[RepoKey.SPECS].forget_files()
    result = await context.imports.import_clusters(
        "agent-owned", await picks(context, LARK), spec_version="1.0.0", user=support.ALICE
    )
    description = result.opened[0].merge_request.description
    assert "Once linked: 2 locked values differ, 0 add-ons missing." in description
    assert "- `owner.anaf`: the file has '56', the flavor locks '99'" in description
    assert (
        "- `nodepool[0].replicas` (nodepool `prod-lark-site1-dell-r660-site1-128c-1024gb-5tb`): "
        "the file has 3, the flavor locks 4"
    ) in description


async def test_each_imported_cluster_follows_the_flavor_once_its_own_mr_merges(
    context: Day1Context, support: Any
) -> None:
    result = await context.imports.import_clusters(
        "agent-baseline",
        await picks(context, LARK, HERON),
        spec_version="1.0.0",
        user=support.ALICE,
    )
    lark = result.opened[0].merge_request
    await context.approvals.approve(RepoKey.DAY1, lark.ref.iid, sha=lark.sha, approver=support.BOB)
    # HERON's MR is still open: only LARK follows the flavor
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
    (opened,) = result.opened
    relinked = gitlab.snapshot(pid, opened.merge_request.source_branch)[str(LARK.path)]
    provenance = read_provenance(relinked)
    assert (provenance.spec_name, provenance.spec_version) == ("agent-baseline", "1.0.0")
    # The values asked for an add-on the new flavor also lists are kept; the rest go.
    assert provenance.requested_addons == (
        RequestedAddon("redbull", "cluster-roles", "main", {"a": 1}),
    )
    assert relinked.endswith(lark.content)
    assert (
        "(it followed flavor `agent-standard` v0.9.0; re-linked on request)"
        in opened.merge_request.description
    )


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


async def test_a_file_that_moved_since_the_preview_opens_no_mr_at_all(
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
    branch = gitlab.snapshot(pid, result.opened[0].merge_request.source_branch)
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


# ── Opening: one MR per cluster, each on its own (ADR-0044) ──────────────────

HAWK = ClusterRef("site1", MCE, "ocp4-prod-hawk-site1")
KARNIOL = ClusterRef("site1", MCE, "ocp4-prod-karniol-site1")
OWL = ClusterRef("site1", MCE, "ocp4-prod-owl-site1")


class Watched:
    """day1's provisioner, watched: what was sent, how many at once, and a hook per cluster."""

    def __init__(
        self,
        real: ClusterProvisioner,
        hooks: Mapping[str, Callable[[], Awaitable[None]]] | None = None,
    ) -> None:
        self.real = real
        self.hooks = hooks or {}
        self.sent: list[str] = []
        self.in_flight = 0
        self.most_in_flight = 0

    async def apply(self, change: ClusterChange) -> ProvisionResult:
        self.sent.append(change.cluster.name)
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)  # let the other opens start, as GitLab's latency would
            hook = self.hooks.get(change.cluster.name)
            if hook is not None:
                await hook()
            return await self.real.apply(change)
        finally:
            self.in_flight -= 1


def watched(
    context: Day1Context,
    gitlab: InMemoryGitLab,
    clock: Any,
    hooks: Mapping[str, Callable[[], Awaitable[None]]] | None = None,
) -> tuple[ImportService, Watched]:
    day1 = cast("CachedRepository", context.repos[RepoKey.DAY1])
    real = GitClusterProvisioner(
        MergeRequestWriter(gitlab, day1, repo=Repo.DAY1, label="day1", clock=clock)
    )
    provisioner = Watched(real, hooks)
    service = ImportService(
        context.clusters, context.specs, context.drift, context.machine_configs, provisioner
    )
    return service, provisioner


async def test_a_file_that_moves_before_its_commit_fails_only_its_own_mr(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab, clock: Any
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    heron = await main_file(gitlab, support, HERON)

    async def someone_edits_heron() -> None:
        await support.push(
            gitlab, support.DAY1, branch="main", file=str(HERON.path), content=heron.content + "#\n"
        )

    service, provisioner = watched(context, gitlab, clock, {HERON.name: someone_edits_heron})
    result = await service.import_clusters(
        "agent-baseline",
        await picks(context, LARK, HERON, HERZI),
        spec_version="1.0.0",
        user=support.ALICE,
    )
    assert [o.cluster for o in result.opened] == [LARK, HERZI]
    ((failed, error),) = [(f.cluster, f.error) for f in result.failed]
    assert failed == HERON
    assert isinstance(error, RevisionConflictError)
    assert provisioner.sent == [LARK.name, HERON.name, HERZI.name]
    assert len(await gitlab.list_merge_requests(pid, state=None)) == 2


async def test_an_unconfirmed_write_is_reported_never_retried_and_starts_no_more_mrs(
    context: Day1Context,
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(imports, "MAX_OPEN_CONCURRENCY", 1)  # one at a time: the order is known

    async def gitlab_times_out() -> None:
        raise AmbiguousWriteError("POST /projects/1/repository/commits timed out after it was sent")

    service, provisioner = watched(context, gitlab, clock, {HERON.name: gitlab_times_out})
    result = await service.import_clusters(
        "agent-baseline",
        await picks(context, LARK, HERON, HERZI),
        spec_version="1.0.0",
        user=support.ALICE,
    )
    assert [o.cluster for o in result.opened] == [LARK]
    (heron, herzi) = result.failed
    assert heron.cluster == HERON
    assert isinstance(heron.error, AmbiguousWriteError)
    # GitLab did not answer: the MRs after it are not sent, and say so
    assert herzi.cluster == HERZI
    assert isinstance(herzi.error, GitUnavailableError)
    assert str(herzi.error) == (
        "not sent: GitLab did not answer for ocp4-prod-heron-site1, so no more merge requests "
        "were started; import this cluster again"
    )
    assert provisioner.sent == [LARK.name, HERON.name]  # HERON once: never retried


async def test_at_most_four_mrs_open_at_once_and_results_keep_the_pick_order(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab, clock: Any
) -> None:
    service, provisioner = watched(context, gitlab, clock)
    chosen = [LARK, HERON, HERZI, KARNIOL, HAWK, OWL]
    result = await service.import_clusters(
        "agent-baseline", await picks(context, *chosen), spec_version="1.0.0", user=support.ALICE
    )
    assert [o.cluster for o in result.opened] == chosen
    assert result.failed == ()
    assert provisioner.most_in_flight == imports.MAX_OPEN_CONCURRENCY == 4
    assert len({o.merge_request.source_branch for o in result.opened}) == len(chosen)
