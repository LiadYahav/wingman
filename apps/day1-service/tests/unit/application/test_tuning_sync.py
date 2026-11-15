"""Syncing a cluster's tuning profiles to its flavor's tuning rule (ADR-0061, ADR-0037).

The fixture cluster ``lark`` names ``tuned-network-latency`` on its first
nodepool and none on its second, and carries a hand-written
``tuningConfigmap`` entry (dev/gitlab-fixtures/README.md). The flavors here
lock only the tuning rule, so configs never move.
"""

from __future__ import annotations

from typing import Any

import yaml

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.domain.paths import ClusterRef

MCE = "ocp4-prod-mce-site1-a"
LARK = ClusterRef("site1", MCE, "ocp4-prod-lark-site1")
LARK_POOLS = (
    "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb",
    "prod-lark-site1-dell-r760-site1-64c-512gb-20tb",
)


def tuned_flavor(name: str, *names: str) -> str:
    tuning = ", ".join(names)
    return f"""apiVersion: wingman.io/v1
kind: ClusterSpec
metadata:
  name: {name}
  version: "1.0.0"
spec:
  day1:
    locked_paths:
      - nodepools[*].tuning_config
    values:
      nodepools:
        - tuning_config: [{tuning}]
  day2:
    addons: []
"""


async def linked(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab, flavor: str, *names: str
) -> str:
    """Lark linked to a new flavor that locks ``names``; lark's text before the link."""
    await support.push(
        gitlab,
        support.SPECS,
        branch="main",
        file=f"specs/{flavor}.yaml",
        content=tuned_flavor(flavor, *names),
    )
    context.repos[RepoKey.SPECS].forget_files()
    pid = await support.project_id(gitlab, support.DAY1)
    before = (await gitlab.read_file(pid, LARK.path, "main")).content
    header = f'# specName: "{flavor}"\n# specVersion: "1.0.0"\n'
    await support.push(
        gitlab, support.DAY1, branch="main", file=str(LARK.path), content=header + before
    )
    context.repos[RepoKey.DAY1].forget_files()
    return before


async def test_drift_names_each_nodepool_whose_profiles_differ_as_a_set(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await linked(
        context, support, gitlab, "agent-tuned", "tuned-sysctl-baseline", "tuned-network-latency"
    )
    plan = await context.sync.preview(LARK, hardware={})
    assert [(str(d.file_key), d.added, d.removed, d.reboots) for d in plan.changes] == [
        ("nodepool[0].tuningConfig", ("tuned-sysctl-baseline",), (), True),
        ("nodepool[1].tuningConfig", ("tuned-sysctl-baseline", "tuned-network-latency"), (), True),
    ]


async def test_a_sync_writes_only_the_names_and_leaves_the_configmap(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    before = await linked(
        context, support, gitlab, "agent-tuned", "tuned-network-latency", "tuned-sysctl-baseline"
    )
    plan = await context.sync.preview(LARK, hardware={})
    assert plan.problems == ()
    values = yaml.safe_load(plan.content)
    assert [p.get("tuningConfig") for p in values["nodepool"]] == [
        ["tuned-network-latency", "tuned-sysctl-baseline"],
        ["tuned-network-latency", "tuned-sysctl-baseline"],
    ]
    # Nothing else moves: the configs, and the CI block with its tuningConfigmap.
    assert values["nodepool"][0]["configs"] == yaml.safe_load(before)["nodepool"][0]["configs"]
    marker = "# === Added by CI ==="
    assert plan.content.split(marker)[1] == before.split(marker)[1]
    assert plan.removals == ()
    assert [(r.nodepool.name, r.configs, r.tuning) for r in plan.rebooting] == [
        (LARK_POOLS[0], False, True),
        (LARK_POOLS[1], False, True),
    ]
    result = await context.sync.sync(
        LARK,
        last_commit_id=plan.cluster.last_commit_id,
        spec_version="1.0.0",
        hardware={},
        confirm_removals=[],
        user=support.ALICE,
    )
    description = result.provision.merge_request.description
    assert (
        f"- `nodepool[1].tuningConfig` (nodepool `{LARK_POOLS[1]}`): add "
        "`tuned-network-latency`, `tuned-sysctl-baseline`"
    ) in description
    assert "**Their nodes may reboot.** The tuning profiles of these nodepools change" in (
        description
    )
    assert "**Merging rolls nodes.**" not in description
    assert "`tuningConfigmap`" in description  # listed among the keys the sync never changes


async def test_a_name_that_does_not_resolve_for_the_cluster_blocks_the_sync(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await linked(context, support, gitlab, "agent-gone", "tuned-gone")
    plan = await context.sync.preview(LARK, hardware={})
    assert plan.problems == (
        "nodepool[0].tuningConfig: tuned-gone is not in tuning/, in tuning/prod-lark-site1/ or "
        "in this file's tuningConfigmap",
        "nodepool[1].tuningConfig: tuned-gone is not in tuning/, in tuning/prod-lark-site1/ or "
        "in this file's tuningConfigmap",
    )


async def test_a_pool_that_already_holds_the_set_in_another_order_is_in_sync(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await linked(context, support, gitlab, "agent-latency", "tuned-network-latency")
    plan = await context.sync.preview(LARK, hardware={})
    assert [str(d.file_key) for d in plan.changes] == ["nodepool[1].tuningConfig"]
    values = yaml.safe_load(plan.content)
    assert values["nodepool"][1]["tuningConfig"] == "tuned-network-latency"


async def test_the_cluster_drift_reports_the_tuning_rule(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await linked(context, support, gitlab, "agent-latency", "tuned-network-latency")
    report = await context.drift.for_cluster(LARK)
    assert [(str(d.file_key), d.flavor_value) for d in report.value_drift] == [
        ("nodepool[1].tuningConfig", "tuned-network-latency")
    ]
