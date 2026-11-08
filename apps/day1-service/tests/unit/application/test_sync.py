"""Syncing a cluster to its flavor, on the seeded in-memory GitLab (ADR-0037).

The fixture clusters ``lark`` and ``heron`` were written by hand before Wingman
(dev/gitlab-fixtures/README.md); the flavor ``agent-baseline`` locks every
nodepool's configs as a rule (ADR-0029).
"""

from __future__ import annotations

from typing import Any

import pytest

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.domain.errors import InvalidInputError, StaleError
from wingman_day1.domain.paths import ClusterRef

MCE = "ocp4-prod-mce-site1-a"
LARK = ClusterRef("site1", MCE, "ocp4-prod-lark-site1")
HERON = ClusterRef("site1", MCE, "ocp4-prod-heron-site1")
HERZI = ClusterRef("site1", MCE, "ocp4-prod-herzi-site1")
LARK_POOLS = (
    "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb",
    "prod-lark-site1-dell-r760-site1-64c-512gb-20tb",
)
LARK_REMOVALS = [(0, "worker-kubeletconfig-reserved"), (1, "restored-example-config")]


def header(flavor: str, version: str = "1.0.0") -> str:
    return f'# specName: "{flavor}"\n# specVersion: "{version}"\n'


async def main_text(gitlab: InMemoryGitLab, support: Any, ref: ClusterRef) -> str:
    pid = await support.project_id(gitlab, support.DAY1)
    return (await gitlab.read_file(pid, ref.path, "main")).content


async def put(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab, ref: ClusterRef, content: str
) -> None:
    await support.push(gitlab, support.DAY1, branch="main", file=str(ref.path), content=content)
    context.repos[RepoKey.DAY1].forget_files()


async def link(
    context: Day1Context,
    support: Any,
    gitlab: InMemoryGitLab,
    ref: ClusterRef,
    flavor: str = "agent-baseline",
    version: str = "1.0.0",
) -> str:
    """Give a fixture file a flavor header on main, as a merged import does; its text before."""
    before = await main_text(gitlab, support, ref)
    await put(context, support, gitlab, ref, header(flavor, version) + before)
    return before


# ── Preview ──────────────────────────────────────────────────────────────────


async def test_the_preview_sets_every_drifted_locked_value_and_nothing_else(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    before = await link(context, support, gitlab, LARK)
    plan = await context.sync.preview(LARK, hardware={})
    assert plan.problems == () and plan.warnings == ()
    # Each nodepool gets exactly the flavor's configs; the entries that stay keep
    # their lines, and the CI block, vlanId and comments do not move.
    expected = header("agent-baseline") + before.replace(
        "  - name: worker-kubeletconfig-reserved\n  - name: nic-ring-buffer\n",
        "  - name: nic-ring-buffer\n",
    ).replace(
        "  - name: restored-example-config  # restored by hand, not onboarded yet\n",
        "  - name: nic-ring-buffer\n",
    )
    assert plan.content == expected
    assert (
        plan.content.split("# === Added by CI ===")[1] == before.split("# === Added by CI ===")[1]
    )
    assert [(r.nodepool.index, r.name) for r in plan.removals] == LARK_REMOVALS
    assert [(r.nodepool.name, r.replicas, r.replaces_nodes) for r in plan.rebooting] == [
        (LARK_POOLS[0], 3, False),
        (LARK_POOLS[1], 2, False),
    ]
    assert [(a.team, a.name) for a in plan.addons_to_install] == [("redbull", "cluster-roles")]
    assert plan.diff.startswith(f"--- a/{LARK.path}\n+++ b/{LARK.path}\n")


async def test_a_cluster_on_no_flavor_cannot_be_synced(context: Day1Context) -> None:
    with pytest.raises(InvalidInputError) as caught:
        await context.sync.preview(LARK, hardware={})
    assert str(caught.value) == "cluster 'ocp4-prod-lark-site1' follows no flavor"


async def test_nodepools_without_one_network_config_wait_for_a_hardware_choice(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    before = await link(context, support, gitlab, HERON)
    waiting = await context.sync.preview(HERON, hardware={})
    assert waiting.problems == (
        "nodepool[0].configs: nodepool[0] has no network config "
        "(nm-conf-prod-heron-site1-<hardware>); choose its hardware type",
        "nodepool[1].configs: nodepool[1] has 2 network configs (nm-conf-prod-heron-site1-dell, "
        "nm-conf-prod-heron-site1-cisco); choose the hardware type it keeps",
    )
    with pytest.raises(InvalidInputError, match="cannot be synced yet"):
        await context.sync.sync(
            HERON,
            last_commit_id=waiting.cluster.last_commit_id,
            spec_version="1.0.0",
            hardware={},
            confirm_removals=[],
            user=support.ALICE,
        )
    chosen = await context.sync.preview(HERON, hardware={0: "dell", 1: "dell"})
    assert chosen.problems == ()
    assert chosen.content == header("agent-baseline") + before.replace(
        "      - name: worker-kubeletconfig-reserved\n      - name: workers-chrony-configuration\n",
        "      - name: workers-chrony-configuration\n"
        "      - name: nm-conf-prod-heron-site1-dell\n"
        "      - name: nic-ring-buffer\n",
    ).replace("      - name: nm-conf-prod-heron-site1-cisco\n", "")
    assert [(r.nodepool.index, r.name) for r in chosen.removals] == [
        (0, "worker-kubeletconfig-reserved"),
        (1, "nm-conf-prod-heron-site1-cisco"),
    ]


async def test_a_hardware_choice_must_be_needed_and_known(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, LARK)
    with pytest.raises(InvalidInputError) as caught:
        await context.sync.preview(LARK, hardware={0: "dell"})
    assert caught.value.problems == (
        "hardware: nodepool[0] needs no hardware choice; its own network config is used",
    )
    await link(context, support, gitlab, HERON)
    with pytest.raises(InvalidInputError) as unknown:
        await context.sync.preview(HERON, hardware={0: "no-such-hardware"})
    (problem,) = unknown.value.problems
    assert problem.startswith("hardware: nodepool[0]")
    assert "no-such-hardware" in problem


async def test_a_file_that_lists_mc_files_warns_about_configs_it_does_not_name(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    before = await link(context, support, gitlab, LARK)
    # The CI renders only what an explicit mcFiles names (ADR-0012); this one lacks nic-ring-buffer.
    await put(
        context,
        support,
        gitlab,
        LARK,
        header("agent-baseline")
        + before.replace("- nic-ring-buffer\n- workers-chrony", "- workers-chrony"),
    )
    (warning,) = (await context.sync.preview(LARK, hardware={})).warnings
    assert warning.startswith(
        "this file lists mcFiles, so the CI renders only the configs it names"
    )
    assert "nic-ring-buffer is not among them" in warning


async def test_a_nodepool_that_replaces_its_nodes_says_so(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    before = await link(context, support, gitlab, LARK)
    replaced = before.replace(
        "  replicas: 2\n", "  replicas: 2\n  upgradeType: Replace\n", 1
    ).replace("  replicas: 3\n", "  replicas: 3\n  inPlace:\n    maxUnavailable: 2\n", 1)
    await put(context, support, gitlab, LARK, header("agent-baseline") + replaced)
    plan = await context.sync.preview(LARK, hardware={})
    first, second = plan.rebooting
    assert (first.upgrade_type, first.max_unavailable, first.replaces_nodes) == (None, 2, False)
    assert (second.upgrade_type, second.replaces_nodes) == ("Replace", True)
    result = await context.sync.sync(
        LARK,
        last_commit_id=plan.cluster.last_commit_id,
        spec_version="1.0.0",
        hardware={},
        confirm_removals=LARK_REMOVALS,
        user=support.ALICE,
    )
    description = result.provision.merge_request.description
    assert (
        f"- `{LARK_POOLS[0]}` (3 nodes): drained and rebooted in place, "
        "`inPlace.maxUnavailable: 2` at a time"
    ) in description
    assert (
        f"- `{LARK_POOLS[1]}` (2 nodes): replaced (`upgradeType: Replace`): new nodes are "
        "provisioned, then the old removed"
    ) in description


# ── Sync ─────────────────────────────────────────────────────────────────────


async def test_a_sync_is_one_mr_that_changes_only_the_cluster_file(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, LARK)
    pid = await support.project_id(gitlab, support.DAY1)
    main_before = gitlab.snapshot(pid, "main")
    plan = await context.sync.preview(LARK, hardware={})
    result = await context.sync.sync(
        LARK,
        last_commit_id=plan.cluster.last_commit_id,
        spec_version="1.0.0",
        hardware={},
        confirm_removals=LARK_REMOVALS,
        user=support.ALICE,
    )
    mr = result.provision.merge_request
    branch = gitlab.snapshot(pid, mr.source_branch)
    assert [p for p in branch if branch[p] != main_before.get(p)] == [str(LARK.path)]
    assert branch[str(LARK.path)] == plan.content
    assert gitlab.snapshot(pid, "main") == main_before
    assert (
        mr.title == "[Wingman/Day1] Sync cluster ocp4-prod-lark-site1 to spec agent-baseline v1.0.0"
    )
    assert mr.description.startswith(
        "Syncing hosted cluster **ocp4-prod-lark-site1** to flavor `agent-baseline` v1.0.0 "
        "(the file followed v1.0.0)."
    )
    assert (
        f"- `nodepool[1].configs` (nodepool `{LARK_POOLS[1]}`): add `nic-ring-buffer`; "
        "**remove** `restored-example-config`"
    ) in mr.description
    assert "**This removes machine configs:** `worker-kubeletconfig-reserved`" in mr.description
    assert f"- `{LARK_POOLS[0]}` (3 nodes): drained and rebooted in place, one node at a time" in (
        mr.description
    )
    assert "install them through day2: `redbull/cluster-roles`." in mr.description
    assert "specVersion" not in mr.description  # the version did not change


async def test_a_sync_must_confirm_exactly_the_configs_it_removes(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, LARK)
    pid = await support.project_id(gitlab, support.DAY1)
    plan = await context.sync.preview(LARK, hardware={})
    with pytest.raises(InvalidInputError) as caught:
        await context.sync.sync(
            LARK,
            last_commit_id=plan.cluster.last_commit_id,
            spec_version="1.0.0",
            hardware={},
            confirm_removals=[(0, "worker-kubeletconfig-reserved"), (0, "nic-ring-buffer")],
            user=support.ALICE,
        )
    assert caught.value.problems == (
        "nodepool[1].configs: the sync removes restored-example-config; confirm it in "
        "confirm_removals",
        "nodepool[0].configs: confirm_removals names nic-ring-buffer, which the sync does not "
        "remove",
    )
    assert await gitlab.list_merge_requests(pid, state=None) == []


async def test_a_file_that_changed_since_the_preview_is_stale(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, LARK)
    plan = await context.sync.preview(LARK, hardware={})
    await put(context, support, gitlab, LARK, plan.cluster.content + "# a later edit\n")
    with pytest.raises(StaleError, match="changed since the preview"):
        await context.sync.sync(
            LARK,
            last_commit_id=plan.cluster.last_commit_id,
            spec_version="1.0.0",
            hardware={},
            confirm_removals=LARK_REMOVALS,
            user=support.ALICE,
        )


async def test_a_sync_after_other_files_changed_is_not_stale(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    # The preview's last_commit_id is the commit the repo was read at (ADR-0035).
    await link(context, support, gitlab, LARK)
    plan = await context.sync.preview(LARK, hardware={})
    await put(context, support, gitlab, HERZI, await main_text(gitlab, support, HERZI) + "# x\n")
    assert (await context.clusters.get(LARK)).last_commit_id != plan.cluster.last_commit_id
    result = await context.sync.sync(
        LARK,
        last_commit_id=plan.cluster.last_commit_id,
        spec_version="1.0.0",
        hardware={},
        confirm_removals=LARK_REMOVALS,
        user=support.ALICE,
    )
    assert result.provision.merge_request.title.startswith("[Wingman/Day1] Sync cluster")


async def test_a_flavor_that_moved_since_the_preview_is_stale(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, LARK)
    plan = await context.sync.preview(LARK, hardware={})
    with pytest.raises(StaleError) as caught:
        await context.sync.sync(
            LARK,
            last_commit_id=plan.cluster.last_commit_id,
            spec_version="0.9.0",
            hardware={},
            confirm_removals=LARK_REMOVALS,
            user=support.ALICE,
        )
    assert str(caught.value) == (
        "flavor agent-baseline is now v1.0.0, not v0.9.0; preview the sync again"
    )


async def test_a_cluster_that_holds_every_locked_value_has_nothing_to_sync(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, LARK, "agent-single")  # a flavor with no locks
    plan = await context.sync.preview(LARK, hardware={})
    assert (plan.changes, plan.changes_file, plan.diff) == ((), False, "")
    with pytest.raises(InvalidInputError, match="already holds every value"):
        await context.sync.sync(
            LARK,
            last_commit_id=plan.cluster.last_commit_id,
            spec_version="1.0.0",
            hardware={},
            confirm_removals=[],
            user=support.ALICE,
        )


async def test_a_file_on_an_older_flavor_version_only_moves_its_header(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    before = await link(context, support, gitlab, LARK, "agent-single", "0.9.0")
    plan = await context.sync.preview(LARK, hardware={})
    assert plan.content == header("agent-single", "1.0.0") + before
    result = await context.sync.sync(
        LARK,
        last_commit_id=plan.cluster.last_commit_id,
        spec_version="1.0.0",
        hardware={},
        confirm_removals=[],
        user=support.ALICE,
    )
    description = result.provision.merge_request.description
    assert "- none; only the header's flavor version changes" in description
    assert "- header: `specVersion` 0.9.0 → 1.0.0" in description


OWNED = """apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: agent-owned
  description: "One team's clusters: its owner number and the first nodepool's size are fixed"
  version: "1.0.0"
  labels:
    platform: agent
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


async def test_scalar_locks_are_set_in_place_and_roll_nothing(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/agent-owned.yaml", content=OWNED
    )
    context.repos[RepoKey.SPECS].forget_files()
    before = await link(context, support, gitlab, LARK, "agent-owned")
    plan = await context.sync.preview(LARK, hardware={})
    assert plan.content == header("agent-owned") + before.replace(
        '  anaf: "56"\n', '  anaf: "99"\n'
    ).replace("  replicas: 3\n", "  replicas: 4\n")
    assert (plan.removals, plan.rebooting, plan.problems) == ((), (), ())
    result = await context.sync.sync(
        LARK,
        last_commit_id=plan.cluster.last_commit_id,
        spec_version="1.0.0",
        hardware={},
        confirm_removals=[],
        user=support.ALICE,
    )
    description = result.provision.merge_request.description
    assert "- `owner.anaf`: '56' → '99'" in description
    assert f"- `nodepool[0].replicas` (nodepool `{LARK_POOLS[0]}`): 3 → 4" in description
    assert "rolls nodes" not in description


async def test_a_linked_file_that_does_not_parse_cannot_be_synced(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await put(context, support, gitlab, LARK, header("agent-baseline") + "nodepool: [\n")
    with pytest.raises(InvalidInputError) as caught:
        await context.sync.preview(LARK, hardware={})
    assert str(caught.value) == "the cluster file does not parse, so Wingman cannot edit it"
