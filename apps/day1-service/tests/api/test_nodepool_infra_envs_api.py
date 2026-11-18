"""A nodepool that draws from several InfraEnvs, over HTTP (ADR-0064).

Off (the default) nothing offers or writes ``additionalInfraEnvNames``: the
form schema leaves the input out, a create or a flavor that sets it is a 422,
and an edit leaves the key as it is (a file that has it still reads and edits).
On, a create writes it, an edit may change it, and three things are refused:
a template that does not render the input, an edit that would rename a
NodePool, and a change of a Replace NodePool's InfraEnvs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.nodepool_infra_envs import FILE_KEY, INPUT, SETTING
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_identity import FakeIdentityProvider

Auth = Callable[[User], dict[str, str]]

DELL, DELL7, HP = (
    "dell-r660-site1-128c-1024gb-5tb",
    "dell-r760-site1-64c-512gb-20tb",
    "hp-gen11-site1-64c",
)
LARK = "ocp4-prod-lark-site1"
BASE = f"/api/day1/clusters/{LARK}"
HOSTED = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"
LARK_PATH = f"{HOSTED}/{LARK}.yaml"
FALCON_PATH = f"{HOSTED}/ocp4-prod-falcon-site1.yaml"
WEBHOOK = {"X-Gitlab-Token": "test-webhook-secret", "X-Gitlab-Event": "Push Hook"}


@pytest.fixture
async def on(
    support: Any,
    gitlab: InMemoryGitLab,
    hub: FakeHubApi,
    identity: FakeIdentityProvider,
    day2: FakeDay2Addons,
    clock: Any,
) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=day2,
        clock=clock,
        day1_multi_infraenv_nodepools=True,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


def create(support: Any, *extra: str, first: str = DELL) -> dict[str, Any]:
    body = support.create_body()
    pools = support.nodepools(first, HP)
    if extra:
        pools[0][INPUT] = list(extra)
    body["variables"]["nodepools"] = pools
    return body


async def opened_file(gitlab: InMemoryGitLab, support: Any, mr: dict[str, Any], path: str) -> str:
    pid = await support.project_id(gitlab, support.DAY1)
    return gitlab.snapshot(pid, mr["source_branch"])[path]


async def modify(
    client: httpx.AsyncClient, headers: dict[str, str], edit: Callable[[str], str]
) -> httpx.Response:
    cluster = (await client.get(BASE, headers=headers)).json()
    return await client.patch(
        BASE,
        json={"updated_yaml": edit(cluster["yaml"]), "last_commit_id": cluster["last_commit_id"]},
        headers=headers,
    )


def with_extra(text: str, *names: str, after: str = f"- infraEnvName: {DELL}\n") -> str:
    return text.replace(after, f"{after}  {FILE_KEY}: [{', '.join(names)}]\n", 1)


def problems(response: httpx.Response) -> list[str]:
    assert response.status_code == 422, response.text
    return response.json()["details"]["problems"]


# ── The form schema ──────────────────────────────────────────────────────────


async def fields(client: httpx.AsyncClient, headers: dict[str, str]) -> list[str]:
    schema = (await client.get("/api/day1/specs/template/schema", headers=headers)).json()
    return [f["name"] for f in next(f for f in schema if f["name"] == "nodepools")["fields"]]


async def test_off_the_form_schema_does_not_offer_the_input_and_on_it_does(
    client: httpx.AsyncClient, on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    assert INPUT not in await fields(client, auth(support.VIEWER))
    assert (await fields(on, auth(support.VIEWER)))[:2] == ["infra_env", INPUT]


# ── Create ───────────────────────────────────────────────────────────────────


async def test_off_a_create_that_sets_extras_is_refused_and_one_without_is_as_before(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    refused = await client.post("/api/day1/clusters", json=create(support, HP), headers=alice)
    assert problems(refused) == [
        f"nodepools[0].{INPUT}: a nodepool draws from its own InfraEnv only in this deployment "
        f"({SETTING} is off)"
    ]
    created = await client.post("/api/day1/clusters", json=create(support), headers=alice)
    assert created.status_code == 201, created.text
    assert FILE_KEY not in await opened_file(gitlab, support, created.json(), FALCON_PATH)


async def test_on_a_create_writes_the_other_infraenvs_after_the_first(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    created = await on.post(
        "/api/day1/clusters", json=create(support, DELL7, HP), headers=auth(support.ALICE)
    )
    assert created.status_code == 201, created.text
    text = await opened_file(gitlab, support, created.json(), FALCON_PATH)
    assert (
        f'  - infraEnvName: {DELL}\n    {FILE_KEY}: ["{DELL7}", "{HP}"]\n    replicas: 2\n' in text
    )
    assert f"  - infraEnvName: {HP}\n    replicas: 2\n" in text, "the second pool is as before"
    assert f"InfraEnv `{DELL}`, also `{DELL7}`, also `{HP}`" in created.json()["description"]


async def test_on_names_that_are_not_infraenvs_are_refused_at_their_field(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = create(support, DELL, "Not An InfraEnv")
    refused = await on.post("/api/day1/clusters/preview", json=body, headers=auth(support.ALICE))
    assert (
        problems(refused)[0]
        == f"nodepools[0].{INPUT}[0]: {DELL} is the nodepool's own InfraEnv already"
    )


async def test_on_a_template_that_does_not_render_the_input_is_refused(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    pid = await support.project_id(gitlab, support.SPECS)
    template = (await on.get("/api/day1/specs/template", headers=auth(support.VIEWER))).json()
    start = template.index("{% if np.additional_infra_envs")
    stale = template[:start] + template[template.index("{% endif %}", start) + 12 :]
    await support.push(
        gitlab, support.SPECS, branch="main", file="cluster-template.j2", content=stale
    )
    await on.post("/api/webhooks/gitlab", json={"project": {"id": pid}}, headers=WEBHOOK)
    assert INPUT not in await fields(on, auth(support.VIEWER)), "the form no longer offers it"
    refused = await on.post(
        "/api/day1/clusters/preview", json=create(support, HP), headers=auth(support.ALICE)
    )
    (problem,) = problems(refused)
    assert problem.startswith(f"nodepool[0].{FILE_KEY}: the template wrote None for ['{HP}']")
    assert "docs/upgrade/3.46-to-3.47.md" in problem
    saved = await on.post("/api/day1/specs", json=flavor(HP), headers=auth(support.ALICE))
    (refused_flavor,) = problems(saved)
    assert refused_flavor.startswith(
        f"nodepools[0].{INPUT}: the specs project's cluster-template.j2 does not read this input"
    )


# ── Flavors ──────────────────────────────────────────────────────────────────


def flavor(*extra: str) -> dict[str, Any]:
    pool = {"infra_env": DELL, **({INPUT: list(extra)} if extra else {})}
    return {
        "apiVersion": "wingman.io/v1",
        "kind": "ClusterSpec",
        "metadata": {"name": "agent-wide", "version": "1.0.0"},
        "spec": {"day1": {"values": {"nodepools": [pool]}}, "day2": {"addons": []}},
    }


async def test_a_flavor_presets_other_infraenvs_only_when_on(
    client: httpx.AsyncClient, on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice = auth(support.ALICE)
    refused = await client.post("/api/day1/specs", json=flavor(HP), headers=alice)
    assert problems(refused) == [
        f"nodepools[0].{INPUT}: a nodepool draws from its own InfraEnv only in this deployment "
        f"({SETTING} is off)"
    ]
    saved = await on.post("/api/day1/specs", json=flavor(HP), headers=alice)
    assert saved.status_code == 201, saved.text


# ── Edits ────────────────────────────────────────────────────────────────────


async def test_off_an_edit_may_not_add_them_but_a_file_that_has_them_reads_and_edits(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    added = await modify(client, alice, lambda y: with_extra(y, HP))
    assert problems(added) == [
        f"nodepool[0]: {FILE_KEY} is not written in this deployment ({SETTING} is off); an "
        "edit must leave it as it is"
    ]
    pid = await support.project_id(gitlab, support.DAY1)
    lark = (await client.get(BASE, headers=alice)).json()["yaml"]
    await support.push(
        gitlab, support.DAY1, branch="main", file=LARK_PATH, content=with_extra(lark, HP)
    )
    await client.post("/api/webhooks/gitlab", json={"project": {"id": pid}}, headers=WEBHOOK)
    read = (await client.get(BASE, headers=alice)).json()
    assert read["values"]["nodepools"][0]["additional_infra_env_names"] == [HP]
    edited = await modify(client, alice, lambda y: y.replace('anaf: "56"', 'anaf: "57"'))
    assert edited.status_code == 200, edited.text
    text = await opened_file(gitlab, support, edited.json(), LARK_PATH)
    assert f"  {FILE_KEY}: [{HP}]\n" in text


async def test_on_an_edit_adds_infraenvs_and_may_not_make_another_one_first(
    on: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    alice = auth(support.ALICE)
    added = await modify(on, alice, lambda y: with_extra(y, HP))
    assert added.status_code == 200, added.text
    renamed = await modify(
        on,
        alice,
        lambda y: y.replace(
            f"- infraEnvName: {DELL}\n", f"- infraEnvName: {HP}\n  {FILE_KEY}: [{DELL}]\n", 1
        ),
    )
    (problem,) = problems(renamed)
    assert problem.startswith(f"nodepool[0]: its first InfraEnv is {HP}, but the NodePool")
    assert f"Keep {DELL} as infraEnvName" in problem


async def test_on_a_replace_nodepools_infraenvs_never_change(
    on: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    alice = auth(support.ALICE)
    pid = await support.project_id(gitlab, support.DAY1)
    lark = (await on.get(BASE, headers=alice)).json()["yaml"]
    replace = lark.replace(
        f"- infraEnvName: {DELL}\n", f"- infraEnvName: {DELL}\n  upgradeType: Replace\n", 1
    )
    await support.push(gitlab, support.DAY1, branch="main", file=LARK_PATH, content=replace)
    await on.post("/api/webhooks/gitlab", json={"project": {"id": pid}}, headers=WEBHOOK)
    refused = await modify(on, alice, lambda y: with_extra(y, HP))
    assert problems(refused) == [
        f"nodepool[0]: NodePool {DELL} is upgradeType Replace, so a change to the InfraEnvs it "
        "draws from would replace every node; leave them as they are"
    ]


# ── Placement ────────────────────────────────────────────────────────────────


async def test_placement_takes_a_need_of_several_infraenvs_as_one_node_type(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get(
        "/api/day1/placement",
        params={"site": "site1", "env": "prod", "need": [f"{HP},{DELL}:3", f"{DELL}:1"]},
        headers=auth(support.VIEWER),
    )
    assert response.status_code == 200, response.text
    assert response.json()["needs"] == [
        {"infra_env": DELL, "infra_envs": [DELL], "replicas": 1},
        {"infra_env": f"{DELL} + {HP}", "infra_envs": [DELL, HP], "replicas": 3},
    ]
    bad = await client.get(
        "/api/day1/placement",
        params={"site": "site1", "env": "prod", "need": f"{DELL},:3"},
        headers=auth(support.VIEWER),
    )
    assert bad.status_code == 422
