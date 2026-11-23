"""Tuning profiles over HTTP (ADR-0061): the catalogue, and the 422s at save, create and edit.

The fixture day1 repo has a ``tuning/`` (dev/gitlab-fixtures/README.md): three
shared Tuned profiles, one PerformanceProfile, a variant of
``tuned-network-latency`` for ``prod-lark-site1`` and one misnamed file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import yaml

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.infrastructure.fake_provision import FakeProvisionWorkflow

Auth = Callable[[User], dict[str, str]]
URL = "/api/day1/tuning-profiles"
LARK = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-lark-site1.yaml"
SECOND_PP = """apiVersion: performance.openshift.io/v2
kind: PerformanceProfile
metadata:
  name: performance-small
spec:
  cpu:
    isolated: "2-7"
    reserved: "0-1"
"""


def flavor(pools: list[dict[str, Any]], locked: list[str] | None = None) -> dict[str, Any]:
    return {
        "apiVersion": "wingman.io/v1",
        "kind": "ClusterSpec",
        "metadata": {"name": "agent-tuned", "version": "1.0.0"},
        "spec": {
            "day1": {"values": {"nodepools": pools}, "locked_paths": locked or []},
            "day2": {"addons": []},
        },
    }


def with_tuning(support: Any, *tuning: object) -> dict[str, Any]:
    body = support.create_body()
    body["variables"]["nodepools"] = [
        {"infra_env": f"dell-r660-site1-pool{i}", "replicas": 2, "tuning_config": t}
        for i, t in enumerate(tuning)
    ]
    return body


async def problems(response: httpx.Response) -> list[str]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    return body["details"]["problems"]


# ── The catalogue ────────────────────────────────────────────────────────────


async def test_the_catalogue_from_the_fixture_repo(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get(URL, headers=auth(support.VIEWER))
    assert response.status_code == 200, response.text

    def profile(name: str, kind: str, summary: str | None, **extra: Any) -> dict[str, Any]:
        return {
            "name": name,
            "kind": kind,
            "summary": summary,
            "path": f"tuning/{name}.yaml",
            "clusters": [],
            "requires_performance_profile": None,
            **extra,
        }

    assert response.json() == {
        "folder": "tuning",
        "found": True,
        "profiles": [
            *(
                profile(f"performance-gpu-{gpu}", "PerformanceProfile", None)
                for gpu in ("b200", "h100", "h200")
            ),
            profile("performance-pinned", "PerformanceProfile", None),
            profile(
                "tuned-conntrack",
                "Tuned",
                "A larger connection-tracking table, with shorter idle timeouts",
            ),
            *(
                profile(
                    f"tuned-gpu-{gpu}",
                    "Tuned",
                    f"{model} workers: no NUMA balancing, memory kept resident",
                    requires_performance_profile=f"performance-gpu-{gpu}",
                )
                for gpu, model in (
                    ("b200", "Blackwell B200"),
                    ("h100", "Hopper H100"),
                    ("h200", "Hopper H200"),
                )
            ),
            profile(
                "tuned-network-latency",
                "Tuned",
                "Lower network latency on worker nodes",
                clusters=["prod-lark-site1"],
            ),
            profile(
                "tuned-pinned-irq",
                "Tuned",
                "Keep interrupts off the pinned CPUs",
                requires_performance_profile="performance-pinned",
            ),
            profile(
                "tuned-readahead",
                "Tuned",
                "Raise the block devices' read-ahead for streaming reads",
            ),
            profile(
                "tuned-sysctl-baseline", "Tuned", "Raise the kernel's file and connection limits"
            ),
        ],
        "problems": [
            {
                "path": "tuning/tuned-misnamed.yaml",
                "detail": (
                    "metadata.name is tuned-renamed; it must be the file's name, tuned-misnamed"
                ),
            }
        ],
    }


async def test_reading_the_catalogue_needs_a_session(client: httpx.AsyncClient) -> None:
    response = await client.get(URL)
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHORIZED")


# ── Flavor save ──────────────────────────────────────────────────────────────


async def test_a_flavor_names_shared_profiles_only(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = flavor(
        [
            {"tuning_config": ["tuned-network-latncy", "performance-pinned"]},
            {"tuning_config": "tuned-misnamed"},
        ]
    )
    response = await client.post("/api/day1/specs", json=body, headers=auth(support.ALICE))
    assert await problems(response) == [
        "nodepools[0].tuning_config[0]: tuned-network-latncy is not a tuning profile in tuning/ "
        "(did you mean tuned-network-latency?)",
        "nodepools[1].tuning_config[0]: tuned-misnamed is not a tuning profile in tuning/",
    ]


async def test_a_flavor_with_the_tuning_rule_is_saved(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    pools = [
        {"tuning_config": ["tuned-pinned-irq", "performance-pinned"]},
        {"tuning_config": ["performance-pinned", "tuned-pinned-irq"]},
    ]
    response = await client.post(
        "/api/day1/specs",
        json=flavor(pools, ["nodepools[*].tuning_config"]),
        headers=auth(support.ALICE),
    )
    assert response.status_code in (200, 201), response.text


async def test_a_tuning_rule_whose_nodepools_disagree_is_refused(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    pools = [{"tuning_config": ["tuned-network-latency"]}, {"tuning_config": []}]
    response = await client.post(
        "/api/day1/specs",
        json=flavor(pools, ["nodepools[*].tuning_config"]),
        headers=auth(support.ALICE),
    )
    assert await problems(response) == [
        "locked_paths: nodepools[*].tuning_config locks every nodepool's tuning profiles, but "
        "spec.day1.values.nodepools[1] sets none"
    ]


async def test_two_performance_profiles_on_one_nodepool_are_refused_at_save(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab, support.DAY1, branch="main", file="tuning/performance-small.yaml", content=SECOND_PP
    )
    body = flavor(
        [{"tuning_config": ["performance-pinned", "tuned-pinned-irq", "performance-small"]}]
    )
    response = await client.post("/api/day1/specs", json=body, headers=auth(support.ALICE))
    assert await problems(response) == [
        "nodepools[0].tuning_config: at most one PerformanceProfile per nodepool (HyperShift); "
        "it names performance-pinned, performance-small"
    ]


# ── Create ───────────────────────────────────────────────────────────────────


async def test_the_preview_writes_one_name_as_a_string_and_several_as_a_list(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = with_tuning(
        support, ["tuned-network-latency"], ["performance-pinned", "tuned-pinned-irq"], []
    )
    response = await client.post(
        "/api/day1/clusters/preview", json=body, headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text
    text = response.json()["yaml"]
    pools = yaml.safe_load(text)["nodepool"]
    assert [p.get("tuningConfig") for p in pools] == [
        "tuned-network-latency",
        ["performance-pinned", "tuned-pinned-irq"],
        None,
    ]
    assert "tuningConfigmap" not in text


async def test_a_create_with_an_unknown_name_is_a_422(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = with_tuning(support, ["tuned-nope"], "tuned-network-latency")
    response = await client.post("/api/day1/clusters", json=body, headers=auth(support.ALICE))
    assert await problems(response) == [
        "nodepools[0].tuning_config[0]: tuned-nope is not a tuning profile in tuning/"
    ]


async def test_a_create_through_provision_cluster_carries_names_and_never_the_configmap(
    support: Any, gitlab: InMemoryGitLab, hub: Any, identity: Any, day2: Any, clock: Any, auth: Auth
) -> None:
    provision = FakeProvisionWorkflow(clock=clock)
    app = support.build_app(
        gitlab=gitlab, hub=hub, identity=identity, day2=day2, clock=clock, provision=provision
    )
    tokens = app.state.session_tokens
    headers = {"Authorization": f"Bearer {tokens.issue(support.ALICE)}"}
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    body = with_tuning(support, ["performance-pinned", "tuned-pinned-irq"], "tuned-sysctl-baseline")
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        response = await client.post("/api/day1/clusters", json=body, headers=headers)
    assert response.status_code == 202, response.text
    (start,) = provision.starts
    values = yaml.safe_load(start["content"])
    assert [p["tuningConfig"] for p in values["nodepool"]] == [
        ["performance-pinned", "tuned-pinned-irq"],
        "tuned-sysctl-baseline",
    ]
    assert "tuningConfigmap" not in start["content"]


# ── Edit ─────────────────────────────────────────────────────────────────────


async def lark(client: httpx.AsyncClient, auth: Auth, support: Any) -> dict[str, Any]:
    response = await client.get(
        "/api/day1/clusters/ocp4-prod-lark-site1", headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def edit(
    client: httpx.AsyncClient, auth: Auth, support: Any, change: Callable[[str], str]
) -> httpx.Response:
    cluster = await lark(client, auth, support)
    return await client.patch(
        "/api/day1/clusters/ocp4-prod-lark-site1",
        json={"updated_yaml": change(cluster["yaml"]), "last_commit_id": cluster["last_commit_id"]},
        headers=auth(support.ALICE),
    )


async def test_an_edit_may_add_a_shared_profile_or_the_cluster_s_own(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await edit(
        client,
        auth,
        support,
        lambda text: text.replace(
            "  - name: restored-example-config  # restored by hand, not onboarded yet\n",
            "  - name: restored-example-config  # restored by hand, not onboarded yet\n"
            "  tuningConfig: [tuned-network-latency, tuned-sysctl-baseline]\n",
        ),
    )
    assert response.status_code in (200, 201), response.text


async def test_an_edit_adding_an_unknown_profile_is_a_422(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await edit(
        client,
        auth,
        support,
        lambda text: text.replace(
            "tuningConfig: tuned-network-latency", "tuningConfig: tuned-nope"
        ),
    )
    assert await problems(response) == [
        "nodepool[0].tuningConfig: tuned-nope is not in tuning/, in tuning/prod-lark-site1/ or in "
        "this file's tuningConfigmap"
    ]


async def test_an_edit_removing_the_tuning_configmap_is_refused(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await edit(
        client, auth, support, lambda text: text.split("\ntuningConfigmap:")[0] + "\n"
    )
    assert await problems(response) == [
        "tuningConfigmap is owned by automation; an edit must leave it as it is"
    ]


async def test_an_edit_of_something_else_ignores_a_name_the_file_already_had(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    context: Day1Context,
) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    text = (await gitlab.read_file(pid, RepoPath(LARK), "main")).content
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file=LARK,
        content=text.replace("tuningConfig: tuned-network-latency", "tuningConfig: tuned-gone"),
    )
    context.repos[RepoKey.DAY1].forget_files()
    response = await edit(
        client, auth, support, lambda text: text.replace("replicas: 3", "replicas: 4")
    )
    assert response.status_code in (200, 201), response.text


async def test_an_explicit_cluster_name_names_the_variant_folder(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    gitlab: InMemoryGitLab,
    context: Day1Context,
) -> None:
    """The CI's ``resolve_cluster_name``: the file's ``clusterName`` key wins over its stem."""
    pid = await support.project_id(gitlab, support.DAY1)
    text = (await gitlab.read_file(pid, RepoPath(LARK), "main")).content
    await support.push(
        gitlab, support.DAY1, branch="main", file=LARK, content="clusterName: lark-x\n" + text
    )
    local = "apiVersion: tuned.openshift.io/v1\nkind: Tuned\nmetadata:\n  name: tuned-local\n"
    await support.push(
        gitlab, support.DAY1, branch="main", file="tuning/lark-x/tuned-local.yaml", content=local
    )
    context.repos[RepoKey.DAY1].forget_files()

    def add(name: str) -> Callable[[str], str]:
        return lambda text: text.replace(
            "tuningConfig: tuned-network-latency", f"tuningConfig: [tuned-network-latency, {name}]"
        )

    assert (await edit(client, auth, support, add("tuned-local"))).status_code in (200, 201)


async def test_a_create_from_the_gpu_flavor_gets_its_locked_profiles_on_every_nodepool(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    """``agent-gpu`` locks the H200 PerformanceProfile, its Tuned and the read-ahead raise."""
    body = support.create_body(spec_name="agent-gpu")
    body["variables"]["nodepools"] = [
        {"infra_env": "dell-r660-site1-128c-1024gb-5tb", "replicas": 2},
        {"infra_env": "hp-gen11-site1-64c", "replicas": 1},
    ]
    response = await client.post(
        "/api/day1/clusters/preview", json=body, headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text
    pools = yaml.safe_load(response.json()["yaml"])["nodepool"]
    assert [p["tuningConfig"] for p in pools] == [
        ["performance-gpu-h200", "tuned-gpu-h200", "tuned-readahead"]
    ] * 2

    body["variables"]["nodepools"][1]["tuning_config"] = ["performance-gpu-b200"]
    refused = await client.post("/api/day1/clusters", json=body, headers=auth(support.ALICE))
    assert await problems(refused) == [
        "nodepools[1].tuning_config: locked by flavor agent-gpu: every nodepool has "
        '["performance-gpu-h200", "tuned-gpu-h200", "tuned-readahead"], in any order; the '
        'request sends ["performance-gpu-b200"]'
    ]
