"""The day2 service as day1 reaches it: its addon list, and its install MRs.

The only place day1 knows day2 exists. Day1 never writes a day2 repo
itself (ADR-0016): ``HttpDay2Addons`` reads what is installed, and
``HttpDay2Installs`` asks day2's own API to open install MRs for a
flavor's rollout (ADR-0044), which day2 opens as for any request, one per
team. Each authenticates with a short-lived session token of day1's own
(the services share the session secret), issued by the injected ``token``
callable, so neither depends on which user's request is being served.

``Day2UnavailableError`` means day2 did not answer usefully: addon state
is then *unknown*, never "nothing installed" (ADR-0004). An install day2
may have acted on but did not confirm says so, and is never resent here
(ADR-0006): the caller reads ``open_installs`` before asking again.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote

import httpx

from wingman_core.domain.mr_conventions import Repo, ResourceType, Verb, mr_title, parse_mr_title
from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.addons import (
    Day2InstallRequest,
    Day2InstallResult,
    InstalledAddon,
    RequestedAddon,
)
from wingman_day1.domain.errors import Day2UnavailableError
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.observed import Day2Operation, Observer, Timer

JSON = Any
"""A decoded JSON value; narrowed where it is read."""

APPROVALS_PATH: Final = "/api/day2/approvals"
"""Day2's open Wingman MRs across every team repo (``list[MRDetailOut]``)."""

NOT_SENT: Final = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
"""Transport errors that happen before a request leaves: nothing reached day2."""

REFUSALS: Final = frozenset({404, 409, 422})
"""Statuses with which day2 refuses an install it did not act on (its RFC 9457 problems)."""

CHECK_FIRST: Final = "Read its open installs on the cluster before asking again."
TEAM_READ_ONLY: Final = "TEAM_READ_ONLY"
"""Day2's 403 for a team that gave Wingman no write access (ADR-0043): that team's refusal."""


def _client(
    base_url: str, timeout_seconds: float, transport: httpx.AsyncBaseTransport | None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(timeout_seconds),
        transport=transport,
        headers={"Accept": "application/json"},
    )


def _addons_path(cluster: ClusterRef, suffix: str = "") -> str:
    return f"/api/day2/clusters/{quote(cluster.name, safe='')}/addons{suffix}"


class HttpDay2Addons:
    """A ``Day2Addons`` over day2's ``GET /api/day2/clusters/{name}/addons``."""

    def __init__(
        self,
        *,
        base_url: str,
        token: Callable[[], str],
        timeout_seconds: float = 5.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Call day2 at ``base_url`` (e.g. ``http://wingman-day2:8002``) as ``token()``."""
        self._token = token
        self._observer = Observer(Dependency.DAY2, metrics, timer=timer)
        self._client = _client(base_url, timeout_seconds, transport)

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        """See Day2Addons.installed."""
        return await self._observer.call(
            Day2Operation.LIST_INSTALLED_ADDONS, self._installed(cluster)
        )

    async def _installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        try:
            response = await self._client.get(
                _addons_path(cluster),
                params={"mce": cluster.mce},
                headers={"Authorization": f"Bearer {self._token()}"},
            )
        except httpx.TransportError as exc:
            raise Day2UnavailableError(
                f"day2 unreachable listing addons of {cluster.name}: {type(exc).__name__}"
            ) from exc
        if response.status_code != 200:
            raise Day2UnavailableError(
                f"day2 answered {response.status_code} listing addons of {cluster.name}"
            )
        try:
            return _installed(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise Day2UnavailableError(
                f"day2 returned a malformed addon list for {cluster.name}"
            ) from exc


class HttpDay2Installs:
    """A ``Day2Installs`` over day2's approvals list and its bulk install.

    ``token`` must issue an *admin* session (day2's bulk install is an
    admin write); the MRs' footers then name its user as the requester.
    A version is never sent: a missing add-on is installed at its team's
    default revision, and any other version would be an emergency pin
    that day2 refuses unless asked for (ADR-0025, ADR-0022).
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: Callable[[], str],
        timeout_seconds: float = 30.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Call day2 at ``base_url`` as ``token()``; an install commits per team, so allow time."""
        self._token = token
        self._observer = Observer(Dependency.DAY2, metrics, timer=timer)
        self._client = _client(base_url, timeout_seconds, transport)

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    async def open_installs(self, cluster: ClusterRef) -> list[Day2InstallRequest]:
        """See Day2Installs.open_installs."""
        return await self._observer.call(
            Day2Operation.LIST_OPEN_INSTALLS, self._open_installs(cluster)
        )

    async def _open_installs(self, cluster: ClusterRef) -> list[Day2InstallRequest]:
        try:
            response = await self._client.get(APPROVALS_PATH, headers=self._auth())
        except httpx.TransportError as exc:
            raise Day2UnavailableError(
                f"day2 unreachable listing its open merge requests: {type(exc).__name__}"
            ) from exc
        if response.status_code != 200:
            raise Day2UnavailableError(
                f"day2 answered {response.status_code} listing its open merge requests"
            )
        try:
            return _open_installs(response.json(), cluster.name)
        except (ValueError, KeyError, TypeError) as exc:
            raise Day2UnavailableError("day2 returned a malformed merge request list") from exc

    async def install(
        self, cluster: ClusterRef, addons: Sequence[RequestedAddon], *, message: str
    ) -> Day2InstallResult:
        """See Day2Installs.install. Nothing to install asks nothing.

        Day2 is asked once per team: day2 validates a whole request before it
        opens anything, so one team that refuses (``TEAM_READ_ONLY``: it gave
        Wingman no write access, ADR-0043) must not hold back the others. A
        team day2 did not answer for is a ``failed`` line saying whether its
        MR may have opened; nothing is retried.
        """
        if not addons:
            return Day2InstallResult(opened=(), failed=())
        teams: dict[str, list[RequestedAddon]] = {}
        for addon in addons:
            teams.setdefault(addon.team, []).append(addon)
        opened: list[Day2InstallRequest] = []
        failed: list[str] = []
        for team, asked in teams.items():
            try:
                result = await self._observer.call(
                    Day2Operation.INSTALL_ADDONS, self._install(cluster, asked, message)
                )
            except Day2UnavailableError as exc:
                failed.append(f"{team}: {exc}")
                continue
            opened += result.opened
            failed += result.failed
        return Day2InstallResult(opened=tuple(opened), failed=tuple(failed))

    async def _install(
        self, cluster: ClusterRef, addons: Sequence[RequestedAddon], message: str
    ) -> Day2InstallResult:
        what = f"the install of {len(addons)} add-on(s) on {cluster.name}"
        body = {
            "addons": [
                {"team": a.team, "addon": a.name, "override_values": dict(a.override_values)}
                for a in addons
            ],
            "custom_message": message,
        }
        try:
            response = await self._client.post(
                _addons_path(cluster, "/bulk"),
                params={"mce": cluster.mce},
                json=body,
                headers=self._auth(),
            )
        except NOT_SENT as exc:
            raise Day2UnavailableError(
                f"day2 could not be reached for {what} ({type(exc).__name__}); nothing was opened"
            ) from exc
        except httpx.TransportError as exc:
            raise Day2UnavailableError(
                f"{what} was sent to day2 but no answer came back ({type(exc).__name__}): day2 "
                f"did not confirm it, so its merge requests may have opened. {CHECK_FIRST}"
            ) from exc
        status = response.status_code
        if status == 201:
            try:
                return _bulk_result(response.json(), cluster.name, addons)
            except (ValueError, KeyError, TypeError) as exc:
                raise Day2UnavailableError(
                    f"day2 accepted {what} (201) but its answer could not be read: its merge "
                    f"requests may have opened. {CHECK_FIRST}"
                ) from exc
        if status in REFUSALS or _code(response) == TEAM_READ_ONLY:
            return Day2InstallResult(opened=(), failed=_refusal(response, team=addons[0].team))
        if status in (401, 403):
            raise Day2UnavailableError(
                f"day2 refused day1's service session ({status}) for {what}: a deployment "
                "problem; nothing was opened"
            )
        if 400 <= status < 500:
            raise Day2UnavailableError(f"day2 answered {status} to {what}; nothing was opened")
        raise Day2UnavailableError(
            f"day2 answered {status} to {what} and did not confirm it: its merge requests may "
            f"have opened. {CHECK_FIRST}"
        )


def _installed(raw: JSON) -> list[InstalledAddon]:
    if not isinstance(raw, dict):
        raise TypeError("the response is not an object")
    items = raw["installed"]
    if not isinstance(items, list):
        raise TypeError("installed is not a list")
    addons: list[InstalledAddon] = []
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("an installed addon is not an object")
        team, name, version = item["team"], item["name"], item.get("version") or ""
        if not (isinstance(team, str) and team and isinstance(name, str) and name):
            raise ValueError("an installed addon has no team or name")
        if not isinstance(version, str):
            raise TypeError("an installed addon's version is not a string")
        addons.append(InstalledAddon(team=team, name=name, version=version))
    return addons


def install_title_charts(title: str, cluster_name: str) -> tuple[str, ...] | None:
    """The charts a day2 install MR's title names on ``cluster_name``; ``None`` if it is not one.

    Day2 titles an install ``[Wingman/Day2] Install addon <team>/<chart>[,<chart>...]
    on <cluster>`` (ADR-0007), ``<cluster>`` being the day1 cluster file's name.
    """
    parsed = parse_mr_title(title)
    if parsed is None or (parsed.repo, parsed.verb, parsed.resource_type) != (
        Repo.DAY2,
        Verb.INSTALL,
        ResourceType.ADDON,
    ):
        return None
    base = mr_title(parsed.repo, parsed.verb, parsed.resource_type, parsed.resource_name)
    if title.removeprefix(base).split()[:2] != ["on", cluster_name]:
        return None
    team, slash, charts = parsed.resource_name.partition("/")
    names = tuple(c for c in charts.split(",") if c)
    return names if team and slash and names else None


def _open_installs(raw: JSON, cluster_name: str) -> list[Day2InstallRequest]:
    if not isinstance(raw, list):
        raise TypeError("the merge request list is not a list")
    found: list[Day2InstallRequest] = []
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("a merge request is not an object")
        title = item["title"]
        if not isinstance(title, str):
            raise TypeError("a merge request's title is not a string")
        charts = install_title_charts(title, cluster_name)
        if charts is not None and item.get("state", "opened") == "opened":
            found.append(_request(item, charts))
    return found


def _request(item: Mapping[str, JSON], charts: tuple[str, ...]) -> Day2InstallRequest:
    team, iid, title, web_url = item["team"], item["iid"], item["title"], item["web_url"]
    if not (isinstance(team, str) and team):
        raise ValueError("a merge request has no team")
    if not isinstance(iid, int) or isinstance(iid, bool) or iid < 1:
        raise TypeError("a merge request's iid is not a positive integer")
    if not (isinstance(title, str) and isinstance(web_url, str)):
        raise TypeError("a merge request's title or web_url is not a string")
    return Day2InstallRequest(team=team, iid=iid, title=title, web_url=web_url, charts=charts)


def _bulk_result(
    raw: JSON, cluster_name: str, addons: Sequence[RequestedAddon]
) -> Day2InstallResult:
    """Day2's ``BulkOut``: an MR per team that opened, and the teams whose MR did not.

    An MR's charts come from its title; one whose title does not read as an
    install keeps the charts day1 asked that team for.
    """
    if not isinstance(raw, dict):
        raise TypeError("the bulk result is not an object")
    merge_requests, failures = raw["merge_requests"], raw["failed"]
    if not (isinstance(merge_requests, list) and isinstance(failures, list)):
        raise TypeError("merge_requests or failed is not a list")
    opened: list[Day2InstallRequest] = []
    for item in merge_requests:
        if not isinstance(item, dict):
            raise TypeError("a merge request is not an object")
        title = item["title"]
        charts = install_title_charts(title, cluster_name) if isinstance(title, str) else None
        requested = tuple(a.name for a in addons if a.team == item["team"])
        opened.append(_request(item, charts or requested))
    failed: list[str] = []
    for failure in failures:
        if not isinstance(failure, dict):
            raise TypeError("a failure is not an object")
        failed.append(
            _line(failure.get("team"), None, failure.get("detail") or failure.get("error"))
        )
    return Day2InstallResult(opened=tuple(opened), failed=tuple(failed))


def _code(response: httpx.Response) -> str | None:
    """A problem answer's ``code``; ``None`` for any other body."""
    try:
        raw = response.json()
    except ValueError:
        return None
    code = raw.get("code") if isinstance(raw, dict) else None
    return code if isinstance(code, str) else None


def _refusal(response: httpx.Response, *, team: str) -> tuple[str, ...]:
    """One line per item day2 refused, from its problem's ``details.problems``; else its detail."""
    status = response.status_code
    try:
        raw = response.json()
    except ValueError:
        return (f"{team}: day2 refused the install ({status})",)
    if not isinstance(raw, dict):
        return (f"{team}: day2 refused the install ({status})",)
    details = raw.get("details")
    details = details if isinstance(details, dict) else {}
    problems = details.get("problems")
    if isinstance(problems, list) and problems:
        lines = [
            _line(p.get("team"), p.get("chart"), p.get("detail"))
            if isinstance(p, dict)
            else _line(None, None, p)
            for p in problems
        ]
        return tuple(lines)
    detail = _one_line(raw.get("detail")) or "no reason given"
    errors = details.get("errors")
    if isinstance(errors, list) and errors:
        detail = f"{detail.rstrip('.')}: " + "; ".join(_validation_error(e) for e in errors)
    return (f"{team}: day2 refused the install ({status}): {detail}",)


def _validation_error(error: JSON) -> str:
    if not isinstance(error, dict):
        return _one_line(error)
    loc = error.get("loc")
    where = ".".join(str(part) for part in loc) if isinstance(loc, list) else ""
    message = _one_line(error.get("msg"))
    return f"{where}: {message}" if where else message


def _line(team: JSON, chart: JSON, detail: JSON) -> str:
    """``<team>[/<chart>]: <detail>``, on one line."""
    who = _one_line(team) or "day2"
    if chart:
        who = f"{who}/{_one_line(chart)}"
    return f"{who}: {_one_line(detail) or 'refused, no reason given'}"


def _one_line(value: JSON) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
