"""FakeDay2Addons: day2's addon list and install MRs over in-memory tables, for tests.

It is both a ``Day2Addons`` and a ``Day2Installs``. ``install`` behaves as
the adapter does, which asks day2 once per team: one MR per team, each with
day2's title, and each team's refusal or failure its own ``failed`` line.
The MRs are what ``open_installs`` lists until a test drops them. Opening an
MR installs nothing: ``installed`` keeps its seed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from wingman_core.domain.mr_conventions import Repo, ResourceType, Verb, mr_title
from wingman_day1.domain.addons import (
    Day2InstallRequest,
    Day2InstallResult,
    InstalledAddon,
    RequestedAddon,
)
from wingman_day1.domain.errors import Day2UnavailableError
from wingman_day1.domain.paths import ClusterRef

FAKE_GITLAB_URL = "https://gitlab.example.com"


class FakeDay2Addons:
    """Day2 as day1 sees it, with hooks a test sets.

    - ``unavailable``: the reads fail like day2 down; ``install`` gives each
      team a ``failed`` line, and nothing opens.
    - ``refuse``: team → why day2 refuses that team's charts (as
      ``TEAM_READ_ONLY`` does, ADR-0043); the other teams' MRs open.
    - ``fail_open``: team → why that team's MR did not open after the
      request was accepted; the other teams' MRs still open.
    - ``unconfirmed``: each team's MR opens, but the answer is a ``failed``
      line saying it may have, like a day2 that timed out.
    - ``install_requests``: every ``install`` call that reached day2, in order.
    """

    def __init__(
        self,
        installed: Mapping[str, Sequence[InstalledAddon]] | None = None,
        *,
        unavailable: bool = False,
        refuse: Mapping[str, str] | None = None,
        fail_open: Mapping[str, str] | None = None,
        unconfirmed: bool = False,
    ) -> None:
        """Seed what day2 reports as installed, keyed by cluster name; the hooks start as given."""
        self._installed = {name: list(addons) for name, addons in (installed or {}).items()}
        self.unavailable = unavailable
        self.refuse: dict[str, str] = dict(refuse or {})
        self.fail_open: dict[str, str] = dict(fail_open or {})
        self.unconfirmed = unconfirmed
        self.install_requests: list[tuple[ClusterRef, tuple[RequestedAddon, ...], str]] = []
        self.open_merge_requests: list[tuple[str, Day2InstallRequest]] = []
        """``(cluster name, MR)`` per open install MR; a test may remove one (merged, closed)."""
        self._iids: dict[str, int] = {}

    def _check_available(self, what: str) -> None:
        if self.unavailable:
            raise Day2UnavailableError(f"day2 unreachable {what} (fake)")

    async def installed(self, cluster: ClusterRef) -> list[InstalledAddon]:
        """See Day2Addons.installed."""
        self._check_available(f"listing addons of {cluster.name}")
        return list(self._installed.get(cluster.name, []))

    async def open_installs(self, cluster: ClusterRef) -> list[Day2InstallRequest]:
        """See Day2Installs.open_installs: matched by cluster name, as day2's titles name it."""
        self._check_available("listing its open merge requests")
        return [mr for name, mr in self.open_merge_requests if name == cluster.name]

    async def install(
        self, cluster: ClusterRef, addons: Sequence[RequestedAddon], *, message: str
    ) -> Day2InstallResult:
        """See Day2Installs.install: per team, as the adapter asks day2.

        A refused team (``refuse``), a team whose MR does not open
        (``fail_open``), day2 down (``unavailable``) or not confirming
        (``unconfirmed``, the MRs open anyway) is a ``failed`` line for that
        team; the other teams' MRs open.
        """
        if not addons:
            return Day2InstallResult(opened=(), failed=())
        by_team: dict[str, list[str]] = {}
        for addon in addons:
            by_team.setdefault(addon.team, []).append(addon.name)
        if self.unavailable:
            return Day2InstallResult(
                opened=(),
                failed=tuple(
                    f"{team}: day2 could not be reached for the install on {cluster.name}; "
                    "nothing was opened (fake)"
                    for team in by_team
                ),
            )
        self.install_requests.append((cluster, tuple(addons), message))
        opened: list[Day2InstallRequest] = []
        failed: list[str] = []
        for team, charts in by_team.items():
            if team in self.refuse:
                failed.append(f"{team}: {self.refuse[team]}")
                continue
            if team in self.fail_open:
                failed.append(f"{team}: {self.fail_open[team]}")
                continue
            request = self._open(team, tuple(charts), cluster.name)
            self.open_merge_requests.append((cluster.name, request))
            if self.unconfirmed:
                failed.append(
                    f"{team}: day2 did not confirm the install on {cluster.name}: its merge "
                    "request may have opened (fake)"
                )
                continue
            opened.append(request)
        return Day2InstallResult(opened=tuple(opened), failed=tuple(failed))

    def _open(self, team: str, charts: tuple[str, ...], cluster_name: str) -> Day2InstallRequest:
        iid = self._iids[team] = self._iids.get(team, 0) + 1
        resource = f"{team}/{','.join(charts)}"
        return Day2InstallRequest(
            team=team,
            iid=iid,
            title=mr_title(
                Repo.DAY2, Verb.INSTALL, ResourceType.ADDON, resource, f"on {cluster_name}"
            ),
            web_url=f"{FAKE_GITLAB_URL}/sigs/{team}/-/merge_requests/{iid}",
            charts=charts,
        )
