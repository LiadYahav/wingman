"""The flavor rules at save and at create, on the seeded in-memory GitLab.

Machine configs resolve by the day1 CI's rule and the network config is
expanded per cluster (ADR-0027); owners are numbers (ADR-0028).
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
