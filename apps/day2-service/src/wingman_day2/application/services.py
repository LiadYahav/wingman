"""Every day2 use case, built once from the ports by the composition root."""

from __future__ import annotations

from dataclasses import dataclass

from wingman_core.ports.clock import Clock
from wingman_core.ports.gitlab import GitLabPort
from wingman_day2.application.approvals import ApprovalService
from wingman_day2.application.audit import AuditService
from wingman_day2.application.catalog import CatalogService
from wingman_day2.application.changes import ChangeService
from wingman_day2.application.installed import InstalledService
from wingman_day2.application.lints import LintService
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
    topology: TopologyService
    catalog: CatalogService
    installed: InstalledService
    preview: PreviewService
    changes: ChangeService
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
        return cls(
            info=GitLabInfo(gitlab_url.rstrip("/"), sigs.group),
            topology=topology,
            catalog=CatalogService(topology, sigs, charts),
            installed=InstalledService(topology, sigs),
            preview=PreviewService(topology, sigs, charts),
            changes=ChangeService(gitlab, topology, sigs, clock),
            approvals=ApprovalService(gitlab, sigs),
            audit=AuditService(gitlab, topology, sigs),
            lints=LintService(topology, sigs, charts),
        )
