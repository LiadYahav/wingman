"""Every day2 use case, built once from the ports by the composition root."""

from __future__ import annotations

from dataclasses import dataclass

from wingman_core.ports.clock import Clock
from wingman_core.ports.gitlab import GitLabPort
from wingman_day2.application.access import AccessService
from wingman_day2.application.approvals import ApprovalService
from wingman_day2.application.audit import AuditService
from wingman_day2.application.authoring import AuthoringService
from wingman_day2.application.catalog import CatalogService
from wingman_day2.application.changes import ChangeService
from wingman_day2.application.fleet_targets import FleetTargetService
from wingman_day2.application.installed import InstalledService
from wingman_day2.application.lints import LintService
from wingman_day2.application.operators import OperatorService
from wingman_day2.application.preview import PreviewService
from wingman_day2.application.topology import TopologyService
from wingman_day2.ports import ChartRepository, Day1Repository, SigsRepository


@dataclass(frozen=True, slots=True)
class GitLabInfo:
    """Where the team repos live, for links in the web app."""

    gitlab_url: str
    sigs_group: str


@dataclass(frozen=True, slots=True)
class Day2Services:
    """The use cases the API calls."""

    info: GitLabInfo
    access: AccessService
    topology: TopologyService
    catalog: CatalogService
    installed: InstalledService
    preview: PreviewService
    changes: ChangeService
    authoring: AuthoringService
    fleet_targets: FleetTargetService
    operators: OperatorService
    approvals: ApprovalService
    audit: AuditService
    lints: LintService

    @classmethod
    def build(
        cls,
        *,
        gitlab: GitLabPort,
        sigs: SigsRepository,
        day1: Day1Repository,
        charts: ChartRepository,
        clock: Clock,
        gitlab_url: str,
    ) -> Day2Services:
        """Wire the use cases to the ports."""
        topology = TopologyService(sigs, day1)
        access = AccessService(sigs)
        catalog = CatalogService(topology, sigs, charts)
        authoring = AuthoringService(gitlab, topology, sigs, charts, access, clock)
        return cls(
            info=GitLabInfo(gitlab_url.rstrip("/"), sigs.group),
            access=access,
            topology=topology,
            catalog=catalog,
            installed=InstalledService(topology, sigs),
            preview=PreviewService(topology, sigs, charts),
            changes=ChangeService(gitlab, topology, sigs, access, clock),
            authoring=authoring,
            fleet_targets=FleetTargetService(gitlab, topology, sigs, charts, access, clock),
            operators=OperatorService(topology, sigs, catalog, authoring, access),
            approvals=ApprovalService(gitlab, sigs, access),
            audit=AuditService(gitlab, topology, sigs),
            lints=LintService(topology, sigs, charts),
        )
