"""Scaling a hosted cluster's NodePools through the platform's update-nodepool workflow (ADR-0062).

The workflow sets one NodePool's replicas, commits them to day1 ``main``,
syncs the cluster's Argo CD Application and checks the NodePool; a
scale-down's leaving servers are its NodePool's policy's. Wingman shows what
can be scaled (the cluster file's NodePools on ``main`` and the flavor's
locks), starts a run and shows it. Day1 checks only what is its own: the
cluster is in the day1 repo, the NodePool is one entry of its file on
``main`` (a start Wingman cannot map to one is refused here, never sent),
and a NodePool whose replicas the cluster's flavor locks is not scaled
except to its locked value (the restore after a sync, ADR-0062). Everything
else (drift between day1 and the MCE, a run or an upgrade already going) is
the workflow's to judge, and its refusal is shown in its words. Who asked is
logged; the orchestrator records nobody. Nothing is retried (ADR-0006).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from wingman_core.domain.users import User
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.domain.cluster_file import load_values
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    InvalidClusterFileError,
    InvalidInputError,
    ResourceNotFoundError,
)
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.scale import (
    FileNodePool,
    ScaleRequest,
    ScaleRun,
    file_nodepools,
    replicas_locks,
    scale_workflow_id,
)
from wingman_day1.ports import ScaleWorkflow

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScaleOptions:
    """What Scale offers for one cluster, from its file on ``main``."""

    ref: ClusterRef
    flavor: str | None
    nodepools: tuple[FileNodePool, ...]


@dataclass(frozen=True, slots=True)
class ScaleTarget:
    """What the person asked: one NodePool, by name, and its replicas."""

    replicas: int
    nodepool: str


class ScaleService:
    """The options, the start and the run of one cluster's NodePool scale."""

    def __init__(
        self, workflow: ScaleWorkflow, clusters: ClusterService, specs: SpecCatalog
    ) -> None:
        """Start and read runs through ``workflow``; the file and its flavor through the rest."""
        self._workflow = workflow
        self._clusters = clusters
        self._specs = specs

    async def options(self, ref: ClusterRef) -> ScaleOptions:
        """The file's NodePools, named by the chart's rule, with the flavor's locks."""
        cluster = await self._clusters.get(ref)
        try:
            values = load_values(cluster.content)
        except InvalidClusterFileError as exc:
            raise InvalidInputError(
                f"cluster {ref.name!r} cannot be scaled: its file does not parse", exc.problems
            ) from exc
        flavor = cluster.provenance.spec_name
        locked = await self._locked(flavor)
        pools = file_nodepools(
            values,
            cluster_name=cluster.hosted_cluster.cluster_name,
            locked=locked,
            flavor=flavor,
        )
        return ScaleOptions(ref, flavor, pools)

    async def start(self, ref: ClusterRef, target: ScaleTarget, *, user: User) -> ScaleRun:
        """Start one run for one NodePool of the file: the workflow commits. Never retried."""
        if target.replicas < 0:
            raise InvalidInputError("replicas cannot be negative", ["replicas must be 0 or more"])
        options = await self.options(ref)
        _refuse_locked(_one_nodepool(options, target.nodepool), target)
        request = ScaleRequest(
            mce_cluster=ref.mce,
            cluster=ref.name,
            replicas=target.replicas,
            nodepool=target.nodepool,
        )
        event = {
            "user": user.username,
            "cluster": ref.name,
            "site": ref.site,
            "mce": ref.mce,
            "replicas": str(target.replicas),
            "target": target.nodepool,
        }
        try:
            run = await self._workflow.start(request)
        except AmbiguousStartError:
            _log(logging.WARNING, "scale start unconfirmed", "scale_start_unconfirmed", event)
            raise
        _log(logging.INFO, "scale started", "scale_started", {**event, "run": run.workflow_id})
        return run

    async def run(self, ref: ClusterRef) -> ScaleRun:
        """The cluster's newest run; ``ResourceNotFoundError`` when it never had one."""
        await self._clusters.hosted_cluster(ref)
        run = await self._workflow.run(scale_workflow_id(ref.name))
        if run is None:
            raise ResourceNotFoundError(f"cluster {ref.name!r} has no scale run")
        return run

    async def _locked(self, flavor: str | None) -> dict[int, int]:
        """The flavor's locked replicas by position; none for no flavor or a deleted one."""
        if not flavor:
            return {}
        try:
            spec = await self._specs.get(flavor)
        except ResourceNotFoundError:
            return {}
        return replicas_locks(spec.locks())


def _one_nodepool(options: ScaleOptions, nodepool: str) -> FileNodePool:
    """The one ``nodepool[]`` entry of the file on ``main`` that renders ``nodepool``.

    update-nodepool sets one NodePool, which must be in day1 under that name;
    a name no entry renders, or two do, is refused here and never sent.
    """
    found = [p for p in options.nodepools if p.name == nodepool]
    if len(found) == 1:
        return found[0]
    if found:
        entries = " and ".join(f"nodepool[{p.index}]" for p in found)
        raise InvalidInputError(
            f"NodePool {nodepool} cannot be scaled",
            [f"{entries} both render NodePool {nodepool}: give each its own name in the day1 file"],
        )
    names = ", ".join(p.name for p in options.nodepools if p.name) or "none"
    raise InvalidInputError(
        f"cluster {options.ref.name!r} has no NodePool {nodepool}",
        [
            f"nodepool: no entry of the day1 file on main renders NodePool {nodepool}; "
            f"its NodePools are {names}"
        ],
    )


def _refuse_locked(pool: FileNodePool, target: ScaleTarget) -> None:
    """A flavor's locked replicas move only back to their locked value (the user, 2026-11-16)."""
    if pool.locked_replicas in (None, target.replicas):
        return
    raise InvalidInputError(
        f"NodePool {pool.label} cannot be scaled",
        [
            f"{pool.label}: its replicas are locked by flavor {pool.locked_by} at "
            f"{pool.locked_replicas}; change the flavor, or restore it to "
            f"{pool.locked_replicas}"
        ],
    )


def _log(level: int, message: str, name: str, event: Mapping[str, str]) -> None:
    fields = " ".join(f"{key}={value}" for key, value in event.items())
    logger.log(level, "%s: %s", message, fields, extra={"event": name, **event})
