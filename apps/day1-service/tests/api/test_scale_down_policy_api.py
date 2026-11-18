"""A nodepool's own scale-down policy over HTTP (ADR-0062): create, the template guard, flavors.

The fixture ``cluster-template.j2`` writes ``nodepools[].scale_down_policy``
as the entry's ``redbull.io/scale-down-policy`` annotation, which the
hostedclusters-setup chart renders onto the NodePool. It needs no setting:
Scale reads it whether or not Scale is on. A specs project whose template
does not read the input refuses a create and a flavor that give it; a
locked policy drifts and a sync writes it; an edit sets only a policy the
workflow knows, and every other edit keeps the annotation as it is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import yaml

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.scale_down_policy import GUIDE, INPUT

Auth = Callable[[User], dict[str, str]]
HOSTED = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"
LARK = "ocp4-prod-lark-site1"
LARK_PATH = f"{HOSTED}/{LARK}.yaml"
KEY = "redbull.io/scale-down-policy"
DELL, HP = "dell-r660-site1-128c-1024gb-5tb", "hp-gen11-site1-64c"
TEMPLATE = (default_fixture_root() / "wingman/cluster-specs/cluster-template.j2").read_text()
_START = TEMPLATE.index("{% if np.scale_down_policy")
OLD_TEMPLATE = TEMPLATE[:_START] + TEMPLATE[TEMPLATE.index("{% endif %}", _START) + 12 :]


async def push(
    client: httpx.AsyncClient,
    support: Any,
    gitlab: InMemoryGitLab,
    project: str,
    file: str,
    text: str,
) -> None:
    """Commit outside Wingman, then tell it, as GitLab's push webhook does."""
    await support.push(gitlab, project, branch="main", file=file, content=text)
    await client.post(
        "/api/webhooks/gitlab",
        json={"project": {"id": await support.project_id(gitlab, project)}},
        headers={"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"},
    )


def create(support: Any, *policies: str | None) -> dict[str, Any]:
    body = support.create_body()
    pools = support.nodepools(DELL, HP)
    for pool, policy in zip(pools, policies, strict=False):
        if policy is not None:
            pool[INPUT] = policy
    body["variables"]["nodepools"] = pools
    return body


def flavor(pool: dict[str, Any], *locked: str) -> dict[str, Any]:
    return {
        "apiVersion": "wingman.io/v1",
        "kind": "ClusterSpec",
        "metadata": {"name": "agent-quiet", "version": "1.0.0"},
        "spec": {
            "day1": {"values": {"nodepools": [pool]}, "locked_paths": list(locked)},
            "day2": {"addons": []},
        },
    }


def problems(response: httpx.Response) -> list[str]:
    assert response.status_code == 422, response.text
    return response.json()["details"]["problems"]


async def modify(
    client: httpx.AsyncClient, headers: dict[str, str], edit: Callable[[str], str]
) -> httpx.Response:
    cluster = (await client.get(f"/api/day1/clusters/{LARK}", headers=headers)).json()
    return await client.patch(
        f"/api/day1/clusters/{LARK}",
        json={"updated_yaml": edit(cluster["yaml"]), "last_commit_id": cluster["last_commit_id"]},
        headers=headers,
    )


def with_policy(text: str, policy: str) -> str:
    first = "  tuningConfig: tuned-network-latency\n"
    return text.replace(first, f"{first}  annotations:\n    {KEY}: {policy}\n", 1)


# ── The form and a create ────────────────────────────────────────────────────


async def test_the_form_offers_the_input_and_a_create_writes_it_only_where_given(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    schema = (
        await client.get("/api/day1/specs/template/schema", headers=auth(support.VIEWER))
    ).json()
    pools = next(f for f in schema if f["name"] == "nodepools")["fields"]
    assert {"name": INPUT, "type": "string", "required": False, "default": ""} in pools
    response = await client.post(
        "/api/day1/clusters/preview",
        json=create(support, "fewest-pods", ""),
        headers=auth(support.ALICE),
    )
    assert response.status_code == 200, response.text
    text = response.json()["yaml"]
    assert f"      allowDeletion: false\n    annotations:\n      {KEY}: fewest-pods\n" in text
    first, second = yaml.safe_load(text)["nodepool"]
    assert (first["annotations"], "annotations" in second) == ({KEY: "fewest-pods"}, False)


async def test_a_policy_the_workflow_does_not_know_is_refused_at_its_field(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.post(
        "/api/day1/clusters/preview",
        json=create(support, None, "random"),
        headers=auth(support.ALICE),
    )
    assert problems(response) == [
        f"nodepools[1].{INPUT}: 'random' is not a scale-down policy update-nodepool knows; use "
        "fewest-pods, least-requested or least-utilized, or none for the platform default"
    ]


async def test_a_template_that_does_not_render_the_input_refuses_a_create_and_a_flavor(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await push(client, support, gitlab, support.SPECS, "cluster-template.j2", OLD_TEMPLATE)
    alice = auth(support.ALICE)
    refused = await client.post(
        "/api/day1/clusters/preview", json=create(support, "fewest-pods"), headers=alice
    )
    (problem,) = problems(refused)
    assert problem.startswith(f"nodepool[0].annotations: the template wrote {KEY} None for")
    assert GUIDE in problem
    plain = await client.post("/api/day1/clusters/preview", json=create(support), headers=alice)
    assert plain.status_code == 200, "without a policy the old template creates as it did"
    saved = await client.post(
        "/api/day1/specs", json=flavor({"infra_env": DELL, INPUT: "fewest-pods"}), headers=alice
    )
    (refused_flavor,) = problems(saved)
    assert refused_flavor.startswith(
        f"nodepools[0].{INPUT}: the specs project's cluster-template.j2 does not read this input"
    )


# ── Flavors: preset, locked, drift and sync ──────────────────────────────────


async def test_a_flavor_presets_or_locks_a_policy_but_never_locks_none(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice = auth(support.ALICE)
    preset = flavor({"infra_env": DELL, INPUT: "least-requested"})
    assert (await client.post("/api/day1/specs", json=preset, headers=alice)).status_code == 201
    none = flavor({"infra_env": DELL, INPUT: ""}, f"nodepools[0].{INPUT}")
    none["metadata"]["name"] = "agent-none"
    (problem,) = problems(await client.post("/api/day1/specs", json=none, headers=alice))
    assert problem.startswith(f"locked_paths: nodepools[0].{INPUT} is locked to no policy")


async def test_a_locked_policy_drifts_and_a_sync_writes_it_as_the_template_does(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    stored = flavor({"infra_env": DELL, INPUT: "fewest-pods"}, f"nodepools[0].{INPUT}")
    await push(
        client, support, gitlab, support.SPECS, "specs/agent-quiet.yaml", yaml.safe_dump(stored)
    )
    pid = await support.project_id(gitlab, support.DAY1)
    before = (await gitlab.read_file(pid, RepoPath(LARK_PATH), "main")).content
    header = '# specName: "agent-quiet"\n# specVersion: "1.0.0"\n'
    await push(client, support, gitlab, support.DAY1, LARK_PATH, header + before)

    drift = (
        await client.get(f"/api/day1/clusters/{LARK}/drift", headers=auth(support.VIEWER))
    ).json()
    assert [(d["file_key"], d["flavor_value"]) for d in drift["value_drift"]] == [
        (f'nodepool[0].annotations["{KEY}"]', "fewest-pods")
    ]
    response = await client.post(
        f"/api/day1/clusters/{LARK}/sync/preview", json={}, headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert (preview["problems"], preview["can_sync"]) == ([], True)
    added = [line[1:] for line in preview["diff"].splitlines() if line.startswith("+ ")]
    assert added == ["  annotations:", f"    {KEY}: fewest-pods"]


# ── Edits ────────────────────────────────────────────────────────────────────


async def test_an_edit_sets_a_known_policy_refuses_another_and_keeps_it_otherwise(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    assert problems(await modify(client, alice, lambda y: with_policy(y, "oldest-first"))) == [
        f"nodepool[0].annotations.{KEY}: 'oldest-first' is not a scale-down policy "
        "update-nodepool knows; use fewest-pods, least-requested or least-utilized, or remove "
        "the annotation"
    ]
    set_ = await modify(client, alice, lambda y: with_policy(y, "least-utilized"))
    assert set_.status_code == 200, set_.text
    lark = (await client.get(f"/api/day1/clusters/{LARK}", headers=alice)).json()["yaml"]
    await push(
        client, support, gitlab, support.DAY1, LARK_PATH, with_policy(lark, "least-utilized")
    )
    edited = await modify(client, alice, lambda y: y.replace('anaf: "56"', 'anaf: "57"'))
    assert edited.status_code == 200, edited.text
    pid = await support.project_id(gitlab, support.DAY1)
    text = gitlab.snapshot(pid, edited.json()["source_branch"])[LARK_PATH]
    assert (
        f"  tuningConfig: tuned-network-latency\n  annotations:\n    {KEY}: least-utilized\n"
        in text
    )
