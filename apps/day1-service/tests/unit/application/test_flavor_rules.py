"""The flavor rules at save and at create, on the seeded in-memory GitLab.

A locked value is the flavor's and a create may not send another
(ADR-0026); machine configs resolve by the day1 CI's rule and the network
config is expanded per cluster (ADR-0027); owners are numbers (ADR-0028).
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.clusters import CreateCluster
from wingman_day1.domain.errors import InvalidInputError, InvalidSpecError
from wingman_day1.domain.specs import ClusterSpec, validate_spec

NEW = "ocp4-prod-falcon-site1"


def flavor(name: str = "agent-flavor", **day1: Any) -> ClusterSpec:
    return validate_spec({"metadata": {"name": name, "version": "1.0.0"}, "spec": {"day1": day1}})


def create(support: Any, *, spec: str = "agent-standard", **variables: Any) -> CreateCluster:
    body = support.create_body(NEW)
    return CreateCluster(
        name=NEW,
        site=body["site"],
        mce=body["mce"],
        spec_name=spec,
        spec_version="1.0.0",
        variables={**body["variables"], **variables},
    )


def pool(*configs: dict[str, str], infra_env: str = "dell-r660-site1-128c-1024gb-5tb") -> dict:
    return {"infra_env": infra_env, "replicas": 2, "configs": list(configs)}


async def committed(gitlab: InMemoryGitLab, support: Any, project: str, branch: str) -> dict:
    pid = await support.project_id(gitlab, project)
    return gitlab.snapshot(pid, branch)


# ── Machine configs at create ────────────────────────────────────────────────


async def test_the_network_config_is_written_for_the_clusters_name(
    context: Day1Context, support: Any
) -> None:
    rendered = await context.clusters.preview(
        create(
            support,
            nodepools=[
                pool({"name": "nm-conf", "hardware": "dell"}, {"name": "nic-ring-buffer"}),
                pool({"name": "nm-conf", "hardware": "dell-data"}, infra_env="hp-gen11-site1-64c"),
            ],
        )
    )
    values = yaml.safe_load(rendered.content)
    assert [p["configs"] for p in values["nodepool"]] == [
        [{"name": "nm-conf-prod-falcon-site1-dell"}, {"name": "nic-ring-buffer"}],
        [{"name": "nm-conf-prod-falcon-site1-dell-data"}],
    ]


async def test_the_network_config_follows_the_cluster_name_setting(
    support: Any, gitlab: InMemoryGitLab, hub: Any, identity: Any, day2: Any, clock: Any
) -> None:
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        day1_cluster_name_strip_prefix="",
    )
    sandbox: Day1Context = app.state.day1
    rendered = await sandbox.clusters.preview(
        create(support, nodepools=[pool({"name": "nm-conf", "hardware": "cisco"})])
    )
    assert "- name: nm-conf-ocp4-prod-falcon-site1-cisco\n" in rendered.content


async def test_every_config_that_does_not_resolve_is_one_problem(
    context: Day1Context, support: Any
) -> None:
    request = create(
        support,
        nodepools=[
            pool({"name": "worker-chrony-configuration"}, {"name": "nm-conf"}),
            pool({"name": "nm-conf", "hardware": "hp"}, {"name": "restored-example-config"}),
        ],
    )
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request)
    assert [p.split(":")[0] for p in caught.value.problems] == [
        "nodepools[0].configs[0]",
        "nodepools[0].configs[1]",
        "nodepools[1].configs[0]",
        "nodepools[1].configs[1]",
    ]
    assert "did you mean 'workers-chrony-configuration'" in caught.value.problems[0]


async def test_a_create_with_an_unknown_config_opens_no_merge_request(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    with pytest.raises(InvalidInputError):
        await context.clusters.create(
            create(support, nodepools=[pool({"name": "typo"})]), user=support.ALICE
        )
    assert await gitlab.list_merge_requests(pid, state=None) == []


async def test_a_flavor_preset_network_config_is_expanded_at_create(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    spec = flavor(
        "agent-net",
        values={"nodepools": [pool({"name": "nm-conf", "hardware": "dell"})]},
    )
    content = yaml.safe_dump(spec.model_dump(mode="json", exclude={"spec": {"day1": {"template"}}}))
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/agent-net.yaml", content=content
    )
    variables = dict(support.create_body(NEW)["variables"])
    del variables["nodepools"]
    rendered = await context.clusters.preview(
        CreateCluster(NEW, support.PROD_SITE, support.PROD_MCE, "agent-net", "1.0.0", variables)
    )
    assert "- name: nm-conf-prod-falcon-site1-dell\n" in rendered.content


# ── Machine configs at flavor save ──────────────────────────────────────────


async def test_a_flavor_keeps_the_network_entry_as_written(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    spec = flavor(
        values={
            "nodepools": [
                {"configs": [{"name": "nm-conf", "hardware": "dell"}, {"name": "nic-ring-buffer"}]}
            ]
        }
    )
    result = await context.specs.create(spec, user=support.ALICE)
    files = await committed(gitlab, support, support.SPECS, result.merge_request.source_branch)
    stored = yaml.safe_load(files["specs/agent-flavor.yaml"])
    assert stored["spec"]["day1"]["values"]["nodepools"][0]["configs"] == [
        {"name": "nm-conf", "hardware": "dell"},
        {"name": "nic-ring-buffer"},
    ]


@pytest.mark.parametrize("action", ["create", "update"])
async def test_a_flavor_whose_configs_do_not_resolve_is_not_saved(
    context: Day1Context, support: Any, action: str
) -> None:
    values = {
        "nodepools": [
            {"configs": [{"name": "nm-conf"}, {"name": "nm-conf-prod-x-site1-dell"}]},
            {"configs": [{"name": "nic-ring-buffer.bu"}]},
        ]
    }
    name = "agent-flavor" if action == "create" else "agent-single"
    with pytest.raises(InvalidSpecError) as caught:
        if action == "create":
            await context.specs.create(flavor(name, values=values), user=support.ALICE)
        else:
            await context.specs.update(name, flavor(name, values=values), user=support.ALICE)
    assert str(caught.value) == f"spec {name!r} cannot be saved"
    assert [p.split(":")[0] for p in caught.value.problems] == [
        "nodepools[0].configs[0]",
        "nodepools[0].configs[1]",
        "nodepools[1].configs[0]",
    ]


async def test_a_flavor_value_that_could_break_the_file_is_not_saved(
    context: Day1Context, support: Any
) -> None:
    spec = flavor(values={"owner_merkaz": "1\nvlanId: 9"})
    with pytest.raises(InvalidSpecError) as caught:
        await context.specs.create(spec, user=support.ALICE)
    assert "one line of plain text" in caught.value.problems[0]


# ── Owners ───────────────────────────────────────────────────────────────────


async def test_owners_that_are_not_numbers_are_refused_at_create(
    context: Day1Context, support: Any
) -> None:
    request = create(support, owner_merkaz="12a4", owner_mador=7)
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request)
    assert [p.split(":")[0] for p in caught.value.problems] == ["owner_merkaz", "owner_mador"]


async def test_owner_and_config_problems_are_reported_together(
    context: Day1Context, support: Any
) -> None:
    request = create(support, owner_anaf="", nodepools=[pool({"name": "typo"})])
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request)
    assert [p.split(":")[0] for p in caught.value.problems] == [
        "owner_anaf",
        "nodepools[0].configs[0]",
    ]


async def test_a_flavor_owner_preset_must_be_a_number(context: Day1Context, support: Any) -> None:
    with pytest.raises(InvalidSpecError) as caught:
        await context.specs.create(flavor(values={"owner_merkaz": "team-a"}), user=support.ALICE)
    assert caught.value.problems[0].startswith("owner_merkaz: must be a number")
    result = await context.specs.create(flavor(values={"owner_merkaz": "0042"}), user=support.ALICE)
    assert result.merge_request.title == "[Wingman/Specs] Create spec agent-flavor"


async def test_a_flavor_preset_owner_is_used_and_checked_at_create(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    spec = flavor("agent-owned", values={"owner_merkaz": "0042"})
    content = yaml.safe_dump(spec.model_dump(mode="json", exclude={"spec": {"day1": {"template"}}}))
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/agent-owned.yaml", content=content
    )
    variables = dict(support.create_body(NEW)["variables"])
    del variables["owner_merkaz"]
    rendered = await context.clusters.preview(
        CreateCluster(NEW, support.PROD_SITE, support.PROD_MCE, "agent-owned", "1.0.0", variables)
    )
    assert yaml.safe_load(rendered.content)["owner"]["merkaz"] == "0042"


# ── Locks ────────────────────────────────────────────────────────────────────

DELL_CONFIGS = [
    {"name": "nm-conf", "hardware": "dell"},
    {"name": "workers-chrony-configuration"},
    {"name": "nic-ring-buffer"},
]


def dell(support: Any, *pools: dict[str, Any]) -> CreateCluster:
    """A create from the agent-dell fixture flavor (nodepools[0].configs locked)."""
    return create(support, spec="agent-dell", nodepools=list(pools))


async def test_a_locked_value_left_out_of_the_request_is_the_flavors(
    context: Day1Context, support: Any
) -> None:
    rendered = await context.clusters.preview(
        dell(
            support,
            {"infra_env": "dell-r660-site1-128c-1024gb-5tb"},
            pool({"name": "nic-ring-buffer"}, infra_env="hp-gen11-site1-64c"),
        )
    )
    pools = yaml.safe_load(rendered.content)["nodepool"]
    assert pools[0]["configs"] == [
        {"name": "nm-conf-prod-falcon-site1-dell"},
        {"name": "workers-chrony-configuration"},
        {"name": "nic-ring-buffer"},
    ]
    assert pools[1]["configs"] == [{"name": "nic-ring-buffer"}]  # not locked


async def test_a_request_that_sends_the_locked_value_is_accepted(
    context: Day1Context, support: Any
) -> None:
    rendered = await context.clusters.preview(dell(support, pool(*DELL_CONFIGS)))
    assert "- name: nm-conf-prod-falcon-site1-dell\n" in rendered.content


async def test_a_request_that_sends_another_value_for_a_lock_is_refused(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    request = dell(support, pool({"name": "nm-conf", "hardware": "cisco"}))
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.create(request, user=support.ALICE)
    (problem,) = caught.value.problems
    assert problem.startswith("nodepools[0].configs: locked by flavor agent-dell to [")
    assert problem.endswith('the request sends [{"name": "nm-conf", "hardware": "cisco"}]')
    assert await gitlab.list_merge_requests(pid, state=None) == []


async def test_a_preset_may_be_overridden(context: Day1Context, support: Any) -> None:
    rendered = await context.clusters.preview(
        dell(support, {"infra_env": "dell-r660-site1-128c-1024gb-5tb", "replicas": 5})
    )
    assert yaml.safe_load(rendered.content)["nodepool"][0]["replicas"] == 5


async def push_flavor(gitlab: InMemoryGitLab, support: Any, spec: dict[str, Any]) -> None:
    name = spec["metadata"]["name"]
    await support.push(
        gitlab,
        support.SPECS,
        branch="main",
        file=f"specs/{name}.yaml",
        content=yaml.safe_dump(spec),
    )


async def test_a_lock_on_a_nodepool_the_request_lacks_is_refused(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await push_flavor(
        gitlab,
        support,
        {
            "metadata": {"name": "agent-two", "version": "1.0.0"},
            "spec": {
                "day1": {
                    "locked_paths": ["nodepools[1].replicas", "owner_anaf"],
                    "values": {"owner_anaf": "56", "nodepools": [{}, {"replicas": 3}]},
                }
            },
        },
    )
    request = create(support, spec="agent-two", nodepools=[pool()], owner_anaf="99")
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request)
    assert caught.value.problems == (
        'owner_anaf: locked by flavor agent-two to "56"; the request sends "99"',
        "nodepools[1].replicas: the flavor locks it to 3, but the cluster has no nodepools[1]",
    )
    replicas_as_text = create(
        support,
        spec="agent-two",
        nodepools=[pool(), {**pool(infra_env="hp-gen11-site1-64c"), "replicas": "3"}],
    )
    rendered = await context.clusters.preview(replicas_as_text)
    assert yaml.safe_load(rendered.content)["owner"]["anaf"] == "56"


async def test_a_stored_legacy_lock_that_fixes_nothing_is_not_enforced(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await push_flavor(
        gitlab,
        support,
        {
            "metadata": {"name": "agent-legacy", "version": "1.0.0"},
            "spec": {"day1": {"immutable_paths": ["cluster_name", "nodepools[0].infra_env"]}},
        },
    )
    entry = await context.specs.entry("agent-legacy")
    assert entry.spec is not None
    assert entry.spec.spec.day1.locked_paths == ["cluster_name", "nodepools[0].infra_env"]
    assert entry.spec.locks() == ()
    await context.clusters.preview(create(support, spec="agent-legacy"))


@pytest.mark.parametrize(
    ("day1", "problem"),
    [
        ({"locked_paths": ["owner_merkaz"]}, "owner_merkaz is locked but spec.day1.values sets"),
        (
            {"locked_paths": ["openshift_release_version"], "values": {}},
            "openshift_release_version is set for each cluster at create",
        ),
        (
            {"immutable_paths": ["nodepools[0].infra_env"], "values": {"nodepools": [{}]}},
            "nodepools[0].infra_env cannot be locked",
        ),
    ],
)
async def test_a_flavor_whose_locks_fix_nothing_lockable_is_not_saved(
    context: Day1Context, support: Any, day1: dict[str, Any], problem: str
) -> None:
    with pytest.raises(InvalidSpecError) as caught:
        await context.specs.create(flavor(**day1), user=support.ALICE)
    (found,) = caught.value.problems
    assert problem in found


async def test_a_flavor_saved_with_the_legacy_name_is_stored_with_the_new_one(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    spec = flavor(immutable_paths=["platform"], values={"platform": "kubevirt"})
    result = await context.specs.create(spec, user=support.ALICE)
    files = await committed(gitlab, support, support.SPECS, result.merge_request.source_branch)
    day1 = yaml.safe_load(files["specs/agent-flavor.yaml"])["spec"]["day1"]
    assert day1["locked_paths"] == ["platform"]
    assert "immutable_paths" not in day1


# ── The configs rule (agent-baseline: nodepools[*].configs) ──────────────────


def baseline(support: Any, *pools: dict[str, Any]) -> CreateCluster:
    """A create from the agent-baseline fixture flavor (every nodepool's configs locked)."""
    return create(support, spec="agent-baseline", nodepools=list(pools))


async def test_the_rule_accepts_its_configs_in_any_order_with_each_nodepools_hardware(
    context: Day1Context, support: Any
) -> None:
    rendered = await context.clusters.preview(
        baseline(
            support,
            pool(*DELL_CONFIGS),
            pool(
                {"name": "nic-ring-buffer"},
                {"name": "workers-chrony-configuration"},
                {"name": "nm-conf", "hardware": "cisco"},
                infra_env="hp-gen11-site1-64c",
            ),
        )
    )
    pools = yaml.safe_load(rendered.content)["nodepool"]
    assert [c["name"] for c in pools[1]["configs"]] == [
        "nic-ring-buffer",
        "workers-chrony-configuration",
        "nm-conf-prod-falcon-site1-cisco",
    ]


async def test_a_nodepool_with_other_configs_than_the_rule_is_refused(
    context: Day1Context, support: Any
) -> None:
    request = baseline(
        support, pool(*DELL_CONFIGS), pool(*DELL_CONFIGS[:2], infra_env="hp-gen11-site1-64c")
    )
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request)
    (problem,) = caught.value.problems
    assert problem.startswith(
        "nodepools[1].configs: locked by flavor agent-baseline: every nodepool has "
        '[{"name": "nm-conf"}, {"name": "workers-chrony-configuration"}, '
        '{"name": "nic-ring-buffer"}]'
    )


async def test_a_nodepool_that_sends_no_configs_gets_the_rule_and_must_pick_its_hardware(
    context: Day1Context, support: Any
) -> None:
    request = baseline(support, pool(*DELL_CONFIGS), {"infra_env": "hp-gen11-site1-64c"})
    with pytest.raises(InvalidInputError) as caught:
        await context.clusters.preview(request)
    assert caught.value.problems == (
        "nodepools[1].configs[0]: nm-conf needs a hardware type, one of cisco, dell, dell-data",
    )


async def test_the_rules_flavor_loads_and_enforces_the_rule(context: Day1Context) -> None:
    entry = await context.specs.entry("agent-baseline")
    assert entry.spec is not None
    assert [str(lock.path) for lock in entry.spec.locks()] == ["nodepools[*].configs"]


async def test_a_rule_whose_nodepools_disagree_is_not_saved(
    context: Day1Context, support: Any
) -> None:
    spec = flavor(
        locked_paths=["nodepools[*].configs"],
        values={"nodepools": [{"configs": DELL_CONFIGS}, {"configs": DELL_CONFIGS[1:]}]},
    )
    with pytest.raises(InvalidSpecError) as caught:
        await context.specs.create(spec, user=support.ALICE)
    assert caught.value.problems == (
        "locked_paths: nodepools[*].configs locks every nodepool to the same configs, but "
        "nodepools[1].configs names other configs than nodepools[0].configs",
    )
