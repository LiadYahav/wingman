"""FakeServerInventory: server-scan in memory (ADR-0038).

Tests seed it directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds it
from ``dev/fleet-fixtures/servers.yaml``, written in server-scan's own row
shape and read by the HTTP adapter's parser (day1's ``fake_fleet.load_fleet``).
It raises the same domain errors as the real adapter. The fake workflows
change its rows as they move a server (``replace``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Final

from wingman_day1.domain.errors import ServerNotFoundError, ServerScanUnavailableError
from wingman_day1.domain.servers import ServerDetail, ServerRow

FLEET_FILE: Final = Path("dev/fleet-fixtures/servers.yaml")


class FakeServerInventory:
    """A ``ServerInventory`` over seeded rows; ``unavailable`` fails every call, as if down."""

    def __init__(self, rows: Iterable[ServerRow] = (), *, unavailable: bool = False) -> None:
        """Seed the fleet."""
        self._rows = {row.id: row for row in rows}
        self.unavailable = unavailable
        self.server_reads = 0
        """How many times ``server`` was called (the uninstall's fresh read)."""
        self._before_read: list[Callable[[], None]] = []

    def before_read(self, hook: Callable[[], None]) -> None:
        """Run ``hook`` before every read: the fake workflow moves its runs on."""
        self._before_read.append(hook)

    def by_id(self, server_id: str) -> ServerRow | None:
        """The server with this id."""
        return self._rows.get(server_id)

    def by_name(self, name: str) -> ServerRow | None:
        """The server with this name, ignoring case."""
        return next((r for r in self._rows.values() if r.name.lower() == name.lower()), None)

    def replace(self, row: ServerRow) -> None:
        """Put ``row`` in place of the server with its id."""
        self._rows[row.id] = row

    def snapshot(self) -> list[ServerRow]:
        """Every server now, by name, without running the read hooks (a fake workflow's look)."""
        return sorted(self._rows.values(), key=lambda row: row.name)

    async def rows(self) -> list[ServerRow]:
        """See ServerInventory.rows: by name."""
        self._read()
        return self.snapshot()

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server."""
        self._read()
        self.server_reads += 1
        row = self._rows.get(server_id)
        if row is None:
            raise ServerNotFoundError(f"server-scan has no server {server_id!r} (fake)")
        return ServerDetail(id=row.id, name=row.name, cluster_name=row.cluster_name)

    def _read(self) -> None:
        if self.unavailable:
            raise ServerScanUnavailableError("server-scan unreachable (fake)")
        for hook in self._before_read:
            hook()


def default_fleet_file() -> Path:
    """``dev/fleet-fixtures/servers.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / FLEET_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{FLEET_FILE} not found above this file")
