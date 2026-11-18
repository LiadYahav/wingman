"""A flavor's image mirrors over HTTP (ADR-0063): save, the template guard, create, drift, sync.

The fixture ``cluster-template.j2`` renders both inputs; a specs project
whose own template does not (``OLD_TEMPLATE``) refuses a flavor that gives
them, warns on a stored one, and refuses a create rather than write a file
without them.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx
import yaml

from wingman_core.domain.git import RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.fixtures import default_fixture_root

Auth = Callable[[User], dict[str, str]]
HOSTED = "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"
LARK = "ocp4-prod-lark-site1"
TEMPLATE = (default_fixture_root() / "wingman/cluster-specs/cluster-template.j2").read_text()
OLD_TEMPLATE = re.sub(
    r"\{% if image_content_sources.*?\{% endif %\}\n\{% if disable_idms_merge.*?\{% endif %\}\n",
    "",
    TEMPLATE,
    flags=re.DOTALL,
)
MIRRORS = [
    {
        "source": "registry.example.com/ocp4/openshift-release-dev",
        "mirrors": ["mirror.example.com/ocp4/openshift-release-dev"],
    },
    {"source": "registry.example.com/operators", "mirrors": ["mirror.example.com/operators"]},
]
GIVEN = {"image_content_sources": MIRRORS, "disable_idms_merge": True}
NO_MIRRORS = (
    "disable_idms_merge: true drops the MCE's default mirrors, and image_content_sources gives "
    "none, so the cluster would have no image mirrors at all; give the cluster's own mirrors, "
    "or keep the MCE's"
)


def flavor(name: str = "agent-mirrors", **day1: Any) -> dict[str, Any]:
    return {
        "apiVersion": "wingman.io/v1",
        "kind": "ClusterSpec",
        "metadata": {"name": name, "version": "1.0.0"},
        "spec": {"day1": day1, "day2": {"addons": []}},
    }


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


async def old_template(client: httpx.AsyncClient, support: Any, gitlab: InMemoryGitLab) -> None:
    await push(client, support, gitlab, support.SPECS, "cluster-template.j2", OLD_TEMPLATE)


def preview_body(support: Any, **variables: Any) -> dict[str, Any]:
    body = support.create_body()
    body["variables"].update(variables)
    return body


# ── Saving a flavor ──────────────────────────────────────────────────────────


async def test_a_flavor_gives_its_mirrors_preset_or_locked(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = flavor(values=GIVEN, locked_paths=["image_content_sources", "disable_idms_merge"])
    response = await client.post("/api/day1/specs", json=body, headers=auth(support.ALICE))
    assert response.status_code == 201, response.text


async def test_a_flavor_that_would_leave_a_cluster_without_mirrors_is_a_422(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = flavor(values={"disable_idms_merge": True})
    response = await client.post("/api/day1/specs", json=body, headers=auth(support.ALICE))
    assert response.status_code == 422
    assert response.json()["details"]["problems"] == [NO_MIRRORS]
    body = flavor(values={"image_content_sources": [{"source": "registry.example.com"}]})
    response = await client.post("/api/day1/specs", json=body, headers=auth(support.ALICE))
    assert response.json()["details"]["problems"] == [
        "image_content_sources[0].mirrors: give at least one mirror, like "
        "mirror.example.com/ocp/release"
    ]


async def test_an_old_template_refuses_a_flavor_with_mirrors_and_warns_on_a_stored_one(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await old_template(client, support, gitlab)
    response = await client.post(
        "/api/day1/specs", json=flavor(values=GIVEN), headers=auth(support.ALICE)
    )
    assert response.status_code == 422
    problems = response.json()["details"]["problems"]
    assert [p.split(":")[0] for p in problems] == ["image_content_sources", "disable_idms_merge"]
    assert problems[0] == (
        "image_content_sources: the specs project's cluster-template.j2 does not read this "
        "input, so a cluster created from this flavor would not get it; add the template lines "
        "in docs/upgrade/3.44-to-3.45.md (ADR-0063)"
    )
    # A flavor without mirrors does not care which template it is
    plain = flavor(name="agent-plain", values={"owner_merkaz": "1234"})
    response = await client.post("/api/day1/specs", json=plain, headers=auth(support.ALICE))
    assert response.status_code == 201, response.text

    stored = flavor(values=GIVEN, locked_paths=["image_content_sources"])
    await push(
        client, support, gitlab, support.SPECS, "specs/agent-mirrors.yaml", yaml.safe_dump(stored)
    )
    read = (await client.get("/api/day1/specs/agent-mirrors", headers=auth(support.VIEWER))).json()
    assert read["warnings"] == problems
    assert read["enforced_locks"] == ["image_content_sources"]


# ── Creating a cluster ───────────────────────────────────────────────────────


async def test_a_create_writes_the_mirrors_it_is_given(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.post(
        "/api/day1/clusters/preview",
        json=preview_body(support, **GIVEN),
        headers=auth(support.ALICE),
    )
    assert response.status_code == 200, response.text
    values = yaml.safe_load(response.json()["yaml"])
    assert (values["imageContentSources"], values["disableIdmsMerge"]) == (MIRRORS, True)

    alone = preview_body(support, disable_idms_merge=True)
    response = await client.post(
        "/api/day1/clusters/preview", json=alone, headers=auth(support.ALICE)
    )
    assert response.status_code == 422
    assert NO_MIRRORS in response.json()["details"]["problems"]


async def test_a_create_against_an_old_template_is_refused_not_written_without_mirrors(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await old_template(client, support, gitlab)
    response = await client.post(
        "/api/day1/clusters/preview",
        json=preview_body(support, **GIVEN),
        headers=auth(support.ALICE),
    )
    assert response.status_code == 422
    problems = response.json()["details"]["problems"]
    assert [p.split(":")[0] for p in problems] == ["imageContentSources", "disableIdmsMerge"]
    assert problems[0].startswith(
        "imageContentSources: the template wrote (absent) for image_content_sources "
        "registry.example.com/ocp4/openshift-release-dev → "
    )
    # Without mirrors, the old template creates clusters as it always did
    response = await client.post(
        "/api/day1/clusters/preview", json=preview_body(support), headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text


# ── Drift and sync ───────────────────────────────────────────────────────────


async def test_locked_mirrors_drift_and_a_sync_writes_them(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    stored = flavor(values=GIVEN, locked_paths=["image_content_sources", "disable_idms_merge"])
    await push(
        client, support, gitlab, support.SPECS, "specs/agent-mirrors.yaml", yaml.safe_dump(stored)
    )
    path = f"{HOSTED}/{LARK}.yaml"
    pid = await support.project_id(gitlab, support.DAY1)
    before = (await gitlab.read_file(pid, RepoPath(path), "main")).content
    header = '# specName: "agent-mirrors"\n# specVersion: "1.0.0"\n'
    await push(client, support, gitlab, support.DAY1, path, header + before)

    drift = (
        await client.get(f"/api/day1/clusters/{LARK}/drift", headers=auth(support.VIEWER))
    ).json()
    assert [
        (d["file_key"], d["flavor_value"], d["cluster_value"]) for d in drift["value_drift"]
    ] == [
        ("imageContentSources", MIRRORS, None),
        ("disableIdmsMerge", True, None),
    ]

    response = await client.post(
        f"/api/day1/clusters/{LARK}/sync/preview", json={}, headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert (preview["problems"], preview["can_sync"]) == ([], True)
    added = [line[1:] for line in preview["diff"].splitlines() if line.startswith("+ ")]
    assert "imageContentSources:" in "\n".join(line for line in preview["diff"].splitlines())
    assert '  - source: "registry.example.com/operators"' in added
    assert "disableIdmsMerge: true" in preview["diff"]
