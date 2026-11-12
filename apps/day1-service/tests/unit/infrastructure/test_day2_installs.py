"""HttpDay2Installs against day2's approvals list and bulk install (MockTransport), and the fake."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.domain.mr_conventions import Repo, ResourceType, Verb, mr_title
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.addons import Day2InstallRequest, Day2InstallResult, RequestedAddon
from wingman_day1.domain.errors import Day2UnavailableError
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.day2_client import HttpDay2Installs, install_title_charts
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons

TOKEN = "rollout-admin-session-never-shown-0001"
CLUSTER = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-hawk-site1")
OTHER = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-lark-site1")
GITLAB = "https://gitlab.example.com"
ADDONS = (
    RequestedAddon("redbull", "bmhgen", "1.2.0", {"replicas": 2}),
    RequestedAddon("redbull", "kyverno", "3.0.0"),
    RequestedAddon("orca", "metrics", ""),
)
REDBULL = ADDONS[:2]
"""One team's add-ons: one request to day2."""

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, metrics: WingmanMetrics | None = None
) -> tuple[HttpDay2Installs, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = HttpDay2Installs(
        base_url="http://wingman-day2.test:8002/",
        token=lambda: TOKEN,
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return client, requests


def reply(status: int, body: object) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def title(team: str, charts: str, cluster: str, verb: Verb = Verb.INSTALL) -> str:
    where = f"from {cluster}" if verb is Verb.REMOVE else f"on {cluster}"
    return mr_title(Repo.DAY2, verb, ResourceType.ADDON, f"{team}/{charts}", where)


def mr(team: str, iid: int, mr_title: str, *, state: str = "opened") -> dict[str, Any]:
    """An ``MRDetailOut`` as day2 serialises it (the fields day1 does not read included)."""
    return {
        "iid": iid,
        "title": mr_title,
        "description": "Install ...\n\n---\nAuthor: system:wingman-rollout\n",
        "author": {"username": "system:wingman-rollout", "name": "", "avatar_url": None},
        "state": state,
        "created_at": "2026-11-12T10:00:00+00:00",
        "updated_at": "2026-11-12T10:00:00+00:00",
        "web_url": f"{GITLAB}/sigs/{team}/-/merge_requests/{iid}",
        "source_branch": f"platform/system-wingman-rollout/install-x-{iid}",
        "target_branch": "main",
        "labels": ["wingman", "day2", "install"],
        "repo": "day2",
        "has_conflicts": False,
        "team": team,
        "project_id": 40 + iid,
        "sha": "a" * 40,
        "gitlab_author": "wingman-bot",
    }


def change(team: str, iid: int, charts: str) -> dict[str, Any]:
    """A ``ChangeOut``: an ``MRDetailOut`` plus what the change writes."""
    return {
        **mr(team, iid, title(team, charts, CLUSTER.name)),
        "cluster": f"hosted:site1:prod:{CLUSTER.mce}:{CLUSTER.name}",
        "files": [{"action": "create", "path": f"sites/.../{charts}/values.yaml"}],
        "app_names": [f"{charts}-{CLUSTER.name}"],
        "warnings": [],
        "notes": [],
    }


def problem(status: int, detail: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """An RFC 9457 problem as day2's handlers write it."""
    return {
        "type": "/problems/validation-error",
        "title": "Validation Error",
        "status": status,
        "detail": detail,
        "instance": f"/api/day2/clusters/{CLUSTER.name}/addons/bulk",
        "code": "VALIDATION_ERROR",
        "request_id": "req_1",
        "details": details or {},
    }


# ── open_installs ───────────────────────────────────────────────────────────


async def test_open_installs_keeps_the_install_mrs_on_this_cluster() -> None:
    body = [
        mr("redbull", 7, title("redbull", "bmhgen,kyverno", CLUSTER.name)),
        mr("orca", 3, title("orca", "metrics", CLUSTER.name)),
        mr("orca", 4, title("orca", "metrics", OTHER.name)),
        mr("orca", 5, title("orca", "metrics", f"{CLUSTER.name}-2")),
        mr("lynx", 2, title("lynx", "backup", CLUSTER.name, Verb.UPDATE)),
        mr("lynx", 3, title("lynx", "backup", CLUSTER.name, Verb.REMOVE)),
        mr("lynx", 4, f"[Wingman/Day1] Install addon lynx/backup on {CLUSTER.name}"),
        mr("lynx", 5, f"Install backup on {CLUSTER.name} by hand"),
        mr("lynx", 6, title("lynx", "backup", CLUSTER.name), state="merged"),
    ]
    client, requests = make(reply(200, body))
    assert await client.open_installs(CLUSTER) == [
        Day2InstallRequest(
            team="redbull",
            iid=7,
            title=title("redbull", "bmhgen,kyverno", CLUSTER.name),
            web_url=f"{GITLAB}/sigs/redbull/-/merge_requests/7",
            charts=("bmhgen", "kyverno"),
        ),
        Day2InstallRequest(
            team="orca",
            iid=3,
            title=title("orca", "metrics", CLUSTER.name),
            web_url=f"{GITLAB}/sigs/orca/-/merge_requests/3",
            charts=("metrics",),
        ),
    ]
    (request,) = requests
    assert (request.method, request.url.path) == ("GET", "/api/day2/approvals")
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.url.host == "wingman-day2.test"
    await client.aclose()


async def test_no_open_mrs_is_no_installs() -> None:
    client, _ = make(reply(200, []))
    assert await client.open_installs(CLUSTER) == []


@pytest.mark.parametrize("status", [401, 403, 404, 500, 503])
async def test_open_installs_on_a_non_200_is_unavailable_not_none(status: int) -> None:
    client, _ = make(reply(status, {"detail": f"echo {TOKEN}"}))
    with pytest.raises(Day2UnavailableError, match=f"answered {status}") as caught:
        await client.open_installs(CLUSTER)
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ReadTimeout])
async def test_open_installs_transport_failures_are_unavailable(
    exc: type[httpx.TransportError],
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc(f"boom {TOKEN}", request=request)

    client, _ = make(fail)
    with pytest.raises(Day2UnavailableError, match=exc.__name__) as caught:
        await client.open_installs(CLUSTER)
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        {"not": "a list"},
        ["nope"],
        [{"iid": 1}],
        [{"title": 3}],
        [{**mr("redbull", 1, title("redbull", "bmhgen", CLUSTER.name)), "iid": "1"}],
        [{**mr("redbull", 1, title("redbull", "bmhgen", CLUSTER.name)), "iid": True}],
        [{**mr("redbull", 1, title("redbull", "bmhgen", CLUSTER.name)), "team": ""}],
        [{**mr("redbull", 1, title("redbull", "bmhgen", CLUSTER.name)), "web_url": None}],
    ],
)
async def test_a_malformed_mr_list_is_unavailable(body: object) -> None:
    client, _ = make(reply(200, body))
    with pytest.raises(Day2UnavailableError, match="malformed"):
        await client.open_installs(CLUSTER)


def test_an_install_title_reads_back_its_charts_on_its_cluster_only() -> None:
    install = title("redbull", "bmhgen,kyverno", CLUSTER.name)
    assert install_title_charts(install, CLUSTER.name) == ("bmhgen", "kyverno")
    assert install_title_charts(install, OTHER.name) is None
    assert install_title_charts(f"{install} (rollout)", CLUSTER.name) == ("bmhgen", "kyverno")
    assert install_title_charts(title("redbull", "", CLUSTER.name), CLUSTER.name) is None
    nameless = mr_title(Repo.DAY2, Verb.INSTALL, ResourceType.ADDON, "bmhgen", f"on {CLUSTER.name}")
    assert install_title_charts(nameless, CLUSTER.name) is None
    bare = mr_title(Repo.DAY2, Verb.INSTALL, ResourceType.ADDON, "redbull/bmhgen")
    assert install_title_charts(bare, CLUSTER.name) is None


# ── install ─────────────────────────────────────────────────────────────────


async def test_install_asks_day2_once_per_team_and_maps_each_team_mr() -> None:
    def by_team(request: httpx.Request) -> httpx.Response:
        team = json.loads(request.content)["addons"][0]["team"]
        if team == "redbull":
            return httpx.Response(
                201, json={"merge_requests": [change("redbull", 7, "bmhgen,kyverno")], "failed": []}
            )
        failed = [{"team": "orca", "error": "GitUnavailableError", "detail": "GitLab\n down"}]
        return httpx.Response(201, json={"merge_requests": [], "failed": failed})

    client, requests = make(by_team)
    result = await client.install(CLUSTER, ADDONS, message="Flavor agent-baseline v1.1.0")
    assert result == Day2InstallResult(
        opened=(
            Day2InstallRequest(
                team="redbull",
                iid=7,
                title=title("redbull", "bmhgen,kyverno", CLUSTER.name),
                web_url=f"{GITLAB}/sigs/redbull/-/merge_requests/7",
                charts=("bmhgen", "kyverno"),
            ),
        ),
        failed=("orca: GitLab down",),
    )
    assert [r.method for r in requests] == ["POST", "POST"]
    assert {r.url.path for r in requests} == {f"/api/day2/clusters/{CLUSTER.name}/addons/bulk"}
    assert all(dict(r.url.params) == {"mce": CLUSTER.mce} for r in requests)
    assert all(r.headers["authorization"] == f"Bearer {TOKEN}" for r in requests)
    # No version: a missing add-on installs at its team's default (ADR-0025).
    assert [json.loads(r.content) for r in requests] == [
        {
            "addons": [
                {"team": "redbull", "addon": "bmhgen", "override_values": {"replicas": 2}},
                {"team": "redbull", "addon": "kyverno", "override_values": {}},
            ],
            "custom_message": "Flavor agent-baseline v1.1.0",
        },
        {
            "addons": [{"team": "orca", "addon": "metrics", "override_values": {}}],
            "custom_message": "Flavor agent-baseline v1.1.0",
        },
    ]
    await client.aclose()


async def test_a_team_that_gave_wingman_no_write_access_does_not_hold_back_the_others() -> None:
    # ADR-0043: day2 answers 403 TEAM_READ_ONLY for that team; it is that team's refusal.
    def by_team(request: httpx.Request) -> httpx.Response:
        team = json.loads(request.content)["addons"][0]["team"]
        if team == "orca":
            body = {
                **problem(403, "orca hasn't given Wingman write access to sigs/orca"),
                "code": "TEAM_READ_ONLY",
                "details": {"team": "orca", "project": "sigs/orca"},
            }
            return httpx.Response(403, json=body)
        return httpx.Response(
            201, json={"merge_requests": [change("redbull", 7, "bmhgen,kyverno")], "failed": []}
        )

    client, _ = make(by_team)
    result = await client.install(CLUSTER, ADDONS, message="m")
    assert [r.team for r in result.opened] == ["redbull"]
    assert result.failed == (
        "orca: day2 refused the install (403): orca hasn't given Wingman write access to sigs/orca",
    )


async def test_an_opened_mr_whose_title_does_not_parse_keeps_the_requested_charts() -> None:
    odd = {**change("redbull", 7, "bmhgen"), "title": "Install bmhgen and kyverno"}
    client, _ = make(reply(201, {"merge_requests": [odd], "failed": []}))
    result = await client.install(CLUSTER, REDBULL, message="m")
    assert [r.charts for r in result.opened] == [("bmhgen", "kyverno")]


async def test_the_cluster_name_is_encoded_into_one_path_segment() -> None:
    client, requests = make(reply(201, {"merge_requests": [], "failed": []}))
    await client.install(ClusterRef("site1", "mce", "odd/../name?x"), REDBULL, message="m")
    assert requests[0].url.raw_path.startswith(
        b"/api/day2/clusters/odd%2F..%2Fname%3Fx/addons/bulk"
    )


async def test_nothing_to_install_asks_day2_nothing() -> None:
    client, requests = make(reply(500, {}))
    assert await client.install(CLUSTER, [], message="m") == Day2InstallResult((), ())
    assert requests == []


async def test_a_bulk_refusal_is_a_result_with_one_line_per_refused_item() -> None:
    refused = problem(
        422,
        "2 of the requested charts cannot be installed; nothing was opened",
        {
            "rule": "bulk",
            "problems": [
                {
                    "team": "redbull",
                    "chart": "kyverno",
                    "detail": "redbull has no\noperators/kyverno/",
                },
                {"team": "orca", "detail": "the change would break the platform's rules: x"},
                "a bare string",
            ],
        },
    )
    client, _ = make(reply(422, refused))
    assert await client.install(CLUSTER, REDBULL, message="m") == Day2InstallResult(
        opened=(),
        failed=(
            "redbull/kyverno: redbull has no operators/kyverno/",
            "orca: the change would break the platform's rules: x",
            "day2: a bare string",
        ),
    )


@pytest.mark.parametrize(
    ("status", "body", "line"),
    [
        (
            404,
            problem(404, f"no destination named {CLUSTER.name}"),
            f"redbull: day2 refused the install (404): no destination named {CLUSTER.name}",
        ),
        (
            409,
            problem(409, "the branch exists already"),
            "redbull: day2 refused the install (409): the branch exists already",
        ),
        (
            422,
            problem(
                422,
                "The request is not valid.",
                {"errors": [{"loc": ["body", "addons", 0, "bogus"], "msg": "Extra inputs"}]},
            ),
            "redbull: day2 refused the install (422): The request is not valid: "
            "body.addons.0.bogus: Extra inputs",
        ),
        (422, ["not", "a problem"], "redbull: day2 refused the install (422)"),
    ],
)
async def test_other_refusals_are_one_line(status: int, body: object, line: str) -> None:
    client, _ = make(reply(status, body))
    assert await client.install(CLUSTER, REDBULL, message="m") == Day2InstallResult((), (line,))


async def test_a_refusal_that_is_not_json_is_one_line() -> None:
    client, _ = make(lambda _r: httpx.Response(404, content=b"<html>"))
    assert await client.install(CLUSTER, REDBULL, message="m") == Day2InstallResult(
        (), ("redbull: day2 refused the install (404)",)
    )


@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_a_server_error_is_unavailable_and_says_the_mrs_may_have_opened(
    status: int,
) -> None:
    client, requests = make(reply(status, {"detail": f"echo {TOKEN}"}))
    result = await client.install(CLUSTER, REDBULL, message="m")
    (line,) = result.failed
    assert (result.opened, line.startswith("redbull: ")) == ((), True)
    assert "may have opened" in line
    assert f"answered {status}" in line
    assert TOKEN not in line
    assert len(requests) == 1  # never retried (ADR-0006)


async def test_an_unreadable_201_is_unavailable_and_says_the_mrs_may_have_opened() -> None:
    client, _ = make(reply(201, {"merge_requests": "nope"}))
    (line,) = (await client.install(CLUSTER, REDBULL, message="m")).failed
    assert re.search(r"^redbull: .*201.*may have opened", line)


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_service_session_is_unavailable_and_nothing_opened(status: int) -> None:
    client, _ = make(reply(status, {}))
    (line,) = (await client.install(CLUSTER, REDBULL, message="m")).failed
    assert re.search(r"^redbull: .*service session.*nothing was opened", line)


async def test_another_client_error_is_unavailable_and_nothing_opened() -> None:
    client, _ = make(reply(405, {}))
    (line,) = (await client.install(CLUSTER, REDBULL, message="m")).failed
    assert re.search(r"^redbull: .*answered 405.*nothing was opened", line)


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
async def test_a_request_that_never_left_is_unavailable_and_nothing_opened(
    exc: type[httpx.TransportError],
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc(f"boom {TOKEN}", request=request)

    client, _ = make(fail)
    (line,) = (await client.install(CLUSTER, REDBULL, message="m")).failed
    assert "nothing was opened" in line
    assert exc.__name__ in line
    assert TOKEN not in line


@pytest.mark.parametrize("exc", [httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError])
async def test_a_request_sent_but_unanswered_says_the_mrs_may_have_opened(
    exc: type[httpx.TransportError],
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc(f"boom {TOKEN}", request=request)

    client, requests = make(fail)
    (line,) = (await client.install(CLUSTER, REDBULL, message="m")).failed
    assert "may have opened" in line
    assert exc.__name__ in line
    assert TOKEN not in line
    assert len(requests) == 1


async def test_calls_are_counted_under_their_own_operations() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    ok, _ = make(reply(200, []), metrics=metrics)
    await ok.open_installs(CLUSTER)
    opened, _ = make(reply(201, {"merge_requests": [], "failed": []}), metrics=metrics)
    await opened.install(CLUSTER, REDBULL, message="m")
    refused, _ = make(reply(422, problem(422, "no")), metrics=metrics)
    await refused.install(CLUSTER, REDBULL, message="m")
    down, _ = make(reply(503, {}), metrics=metrics)
    assert (await down.install(CLUSTER, REDBULL, message="m")).opened == ()

    def count(operation: str, outcome: str) -> float | None:
        return metrics.registry.get_sample_value(
            "wingman_dependency_requests_total",
            {"dependency": "day2", "operation": operation, "outcome": outcome},
        )

    assert count("list_open_installs", "ok") == 1
    assert count("install_addons", "ok") == 2  # day2 answered: an MR per team, or why not
    assert count("install_addons", "unavailable") == 1


# ── the fake ────────────────────────────────────────────────────────────────


async def test_the_fake_opens_one_mr_per_team_and_lists_them_as_open() -> None:
    fake = FakeDay2Addons()
    result = await fake.install(CLUSTER, ADDONS, message="rollout")
    assert result.failed == ()
    assert [(r.team, r.iid, r.charts) for r in result.opened] == [
        ("redbull", 1, ("bmhgen", "kyverno")),
        ("orca", 1, ("metrics",)),
    ]
    redbull = result.opened[0]
    assert redbull.web_url == "https://gitlab.example.com/sigs/redbull/-/merge_requests/1"
    # The fake's titles are day2's: the real adapter reads them back.
    assert install_title_charts(redbull.title, CLUSTER.name) == ("bmhgen", "kyverno")
    assert await fake.open_installs(CLUSTER) == list(result.opened)
    assert await fake.open_installs(OTHER) == []
    assert fake.install_requests == [(CLUSTER, ADDONS, "rollout")]

    again = await fake.install(OTHER, ADDONS[:1], message="m")
    assert [(r.team, r.iid) for r in again.opened] == [("redbull", 2)]
    assert await fake.open_installs(OTHER) == list(again.opened)
    assert await fake.installed(CLUSTER) == []  # an open MR installs nothing


async def test_a_refused_team_in_the_fake_holds_back_only_itself() -> None:
    fake = FakeDay2Addons(refuse={"orca": "orca hasn't given Wingman write access"})
    result = await fake.install(CLUSTER, ADDONS, message="m")
    assert [r.team for r in result.opened] == ["redbull"]
    assert result.failed == ("orca: orca hasn't given Wingman write access",)
    assert [r.team for r in await fake.open_installs(CLUSTER)] == ["redbull"]
    assert len(fake.install_requests) == 1


async def test_a_team_whose_mr_fails_to_open_leaves_the_others_open() -> None:
    fake = FakeDay2Addons(fail_open={"redbull": "GitLab is unavailable"})
    result = await fake.install(CLUSTER, ADDONS, message="m")
    assert [r.team for r in result.opened] == ["orca"]
    assert result.failed == ("redbull: GitLab is unavailable",)


async def test_an_unconfirmed_install_in_the_fake_says_so_but_its_mrs_are_open() -> None:
    fake = FakeDay2Addons(unconfirmed=True)
    result = await fake.install(CLUSTER, ADDONS, message="m")
    assert result.opened == ()
    assert all("may have opened" in line for line in result.failed)
    assert [r.team for r in await fake.open_installs(CLUSTER)] == ["redbull", "orca"]


async def test_the_fake_down_fails_every_call_and_records_no_install() -> None:
    fake = FakeDay2Addons(unavailable=True)
    with pytest.raises(Day2UnavailableError):
        await fake.open_installs(CLUSTER)
    result = await fake.install(CLUSTER, ADDONS, message="m")
    assert result.opened == ()
    assert [line.split(":")[0] for line in result.failed] == ["redbull", "orca"]
    assert fake.install_requests == []
    assert await fake.install(CLUSTER, [], message="m") == Day2InstallResult((), ())
