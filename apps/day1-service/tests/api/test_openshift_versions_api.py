"""``GET /api/day1/mces/{mce}/openshift-versions``, and create refusing what the MCE can't host.

The versions come from the day1 repo's ``upgrade/`` folder (ADR-0034), read
from the fixtures through the in-memory GitLab.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

Auth = Callable[[User], dict[str, str]]

PROD = "ocp4-prod-mce-site1-a"
PREP = "ocp4-prep-mce-site1-a"


async def remove(gitlab: InMemoryGitLab, support: Any, path: str) -> None:
    pid = await support.project_id(gitlab, support.DAY1)
    current = await gitlab.read_file(pid, RepoPath(path), "main")
    await gitlab.commit(
        pid,
        branch="main",
        message=f"remove {path}",
        changes=[FileChange.delete(RepoPath(path), last_commit_id=current.last_commit_id)],
    )


async def versions(client: httpx.AsyncClient, auth: Auth, support: Any, mce: str) -> Any:
    response = await client.get(
        f"/api/day1/mces/{mce}/openshift-versions", headers=auth(support.VIEWER)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_each_mce_offers_the_ladder_rungs_of_its_own_minors(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    assert await versions(client, auth, support, PROD) == {
        "mce": PROD,
        "versions": ["4.18.56", "4.17.58", "4.16.55"],
        "problems": [],
    }
    prep = await versions(client, auth, support, PREP)
    assert prep["versions"] == ["4.21.40", "4.20.44", "4.19.53", "4.18.56", "4.17.58"]
    # The sandbox MCE hosts 4.14 and 4.22 too, but the ladder has no rung in them.
    sandbox = await versions(client, auth, support, "ocp4-mce-workflow-test")
    assert sandbox["versions"][0] == "4.21.40"
    assert sandbox["versions"][-1] == "4.15.41"


async def test_an_mce_without_its_upgrade_file_offers_nothing_and_says_why(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await remove(gitlab, support, f"upgrade/mces/{PROD}.yaml")
    body = await versions(client, auth, support, PROD)
    assert body["versions"] == []
    assert body["problems"] == [
        f"MCE {PROD} has no upgrade/mces/{PROD}.yaml in the day1 repo, so Wingman can't tell "
        "which OpenShift versions it can host. Add it (see upgrade/README.md)."
    ]


async def test_without_a_ladder_no_mce_offers_a_version(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await remove(gitlab, support, "upgrade/ladder.yaml")
    body = await versions(client, auth, support, PREP)
    assert body["versions"] == []
    assert body["problems"][0].startswith("The day1 repo has no upgrade/ladder.yaml")


async def test_a_broken_mce_file_is_a_problem_not_an_error(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await support.push(
        gitlab,
        support.DAY1,
        branch="main",
        file=f"upgrade/mces/{PROD}.yaml",
        content="mce:\n  supportedHostedVersions: [4.20, '4.18']\n",
    )
    body = await versions(client, auth, support, PROD)
    assert body["versions"] == ["4.18.56"]
    assert "is the number 4.2" in body["problems"][0]


async def test_an_mce_that_exists_nowhere_is_not_found(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await client.get(
        "/api/day1/mces/ocp4-prod-mce-site9-z/openshift-versions", headers=auth(support.VIEWER)
    )
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_create_and_preview_refuse_a_release_the_mce_cannot_host(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = support.create_body()
    body["variables"]["openshift_release_version"] = "4.20.44-x86_64"
    for route in ("/api/day1/clusters/preview", "/api/day1/clusters"):
        response = await client.post(route, json=body, headers=auth(support.ALICE))
        assert response.status_code == 422, route
        problem = response.json()
        assert problem["detail"] == f"OpenShift 4.20.44-x86_64 is not offered on MCE {PROD}"
        assert problem["details"]["problems"] == [
            f"MCE {PROD} can host 4.18.56, 4.17.58, 4.16.55; 4.20.44 is not one of them"
        ]


async def test_create_refuses_every_release_on_an_mce_without_its_upgrade_file(
    client: httpx.AsyncClient, auth: Auth, support: Any, gitlab: InMemoryGitLab
) -> None:
    await remove(gitlab, support, f"upgrade/mces/{PROD}.yaml")
    response = await client.post(
        "/api/day1/clusters/preview", json=support.create_body(), headers=auth(support.ALICE)
    )
    assert response.status_code == 422
    problems = response.json()["details"]["problems"]
    assert problems[0] == f"MCE {PROD} offers no OpenShift version"
    assert f"has no upgrade/mces/{PROD}.yaml" in problems[1]


async def test_a_release_with_its_architecture_suffix_is_accepted(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    # The ladder writes 4.18.56; the request's 4.18.56-x86_64 is the same release.
    response = await client.post(
        "/api/day1/clusters/preview", json=support.create_body(), headers=auth(support.ALICE)
    )
    assert response.status_code == 200, response.text
    assert "mastertag: 4.18.56-x86_64" in response.json()["yaml"]
