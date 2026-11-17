"""server-scan's part of the fake fleet: its fake, seeded from ``dev/fleet-fixtures`` (ADR-0048).

``DAY1_FAKE_FLEET=true`` (development only): the fleet's servers, and beside
them what each Server Scan page reads: the rules and policies, the site
catalog, the records, the Claude skill, the architecture diagrams, the
hardware catalog, the audit trail and the Jobs. ``platform_adapters`` calls
this; nothing else does.
"""

from __future__ import annotations

from collections.abc import Sequence

from wingman_core.ports.clock import Clock
from wingman_day1.domain.servers import ServerRow
from wingman_day1.integrations.server_scan.infrastructure.fakes.architecture import (
    default_diagram_file,
    load_diagrams,
)
from wingman_day1.integrations.server_scan.infrastructure.fakes.confs import (
    default_confs_file,
    load_confs,
)
from wingman_day1.integrations.server_scan.infrastructure.fakes.events import (
    default_events_file,
    load_events,
)
from wingman_day1.integrations.server_scan.infrastructure.fakes.inventory import (
    FakeServerInventory,
    default_fleet_file,
)
from wingman_day1.integrations.server_scan.infrastructure.fakes.jobs import demo_jobs
from wingman_day1.integrations.server_scan.infrastructure.fakes.records import (
    default_records_file,
    load_records,
)
from wingman_day1.integrations.server_scan.infrastructure.fakes.rules import (
    default_rules_file,
    load_rules,
)
from wingman_day1.integrations.server_scan.infrastructure.fakes.sites import load_site_catalog
from wingman_day1.integrations.server_scan.infrastructure.fakes.skill import (
    default_skill_dir,
    load_skill,
)


def fleet_inventory(rows: Sequence[ServerRow], *, clock: Clock) -> FakeServerInventory:
    """The fake server-scan over the fleet's ``rows``, with every other fixture beside them."""
    return FakeServerInventory(
        rows,
        rules=load_rules(default_rules_file()),
        sites=load_site_catalog(default_fleet_file()),
        records=load_records(default_records_file()),
        skill=load_skill(default_skill_dir()),
        diagrams=load_diagrams(default_diagram_file()),
        confs=load_confs(default_confs_file()),
        events=load_events(default_events_file(), rows),
        jobs=demo_jobs(clock),
        clock=clock,
    )
