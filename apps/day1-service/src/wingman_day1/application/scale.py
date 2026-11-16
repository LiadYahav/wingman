"""Scaling a hosted cluster's NodePools through the platform's update-nodepool workflow (ADR-0062).

The workflow plans the replicas, commits them to day1 ``main``, syncs the
cluster's Argo CD Application and checks the NodePools; a scale-down's
leaving servers are its NodePools' policy's. Wingman shows what can be
scaled (the cluster file's NodePools on ``main``, their InfraEnv kinds and
the flavor's locks), starts a run and shows it. Day1 checks only what is its
own: the cluster is in the day1 repo, and a NodePool whose replicas the
cluster's flavor locks is not scaled, by name or by a kind that selects it,
except to its locked value (the restore after a sync, ADR-0062). Everything
else (an unknown kind or name, NodePools out of balance, drift between day1
and the MCE, a run or an upgrade already going) is the workflow's to judge,
and its refusal is shown in its words. Who asked is logged; the orchestrator
records nobody. Nothing is retried (ADR-0006).
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
    KindChoice,
    ScaleRequest,
    ScaleRun,
    belongs_to_kind,
    file_nodepools,
    kind_choices,
    replicas_locks,
    scale_workflow_id,
)
from wingman_day1.ports import ScaleWorkflow

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScaleOptions:
    """What the Scale dialog offers for one cluster, from its file on ``main``."""

    ref: ClusterRef
    flavor: str | None
    nodepools: tuple[FileNodePool, ...]
    kinds: tuple[KindChoice, ...]


@dataclass(frozen=True, slots=True)
class ScaleTarget:
    """What the person asked: the replicas, and exactly one of a kind (a total) or a NodePool."""

    replicas: int
    infra_env_kind: str | None = None
    nodepool: str | None = None


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
        """The file's NodePools with the flavor's locks, and the kinds a total may be spread on."""
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
        return ScaleOptions(ref, flavor, pools, kind_choices(pools))

    async def start(self, ref: ClusterRef, target: ScaleTarget, *, user: User) -> ScaleRun:
        """Start one run: the workflow plans and commits. Never retried."""
        if (target.infra_env_kind is None) == (target.nodepool is None):
            raise InvalidInputError(
                "choose one target", ["send exactly one of infra_env_kind and nodepool"]
            )
        if target.replicas < 0:
            raise InvalidInputError("replicas cannot be negative", ["replicas must be 0 or more"])
        options = await self.options(ref)
        _refuse_locked(options, target)
        request = ScaleRequest(
            mce_cluster=ref.mce,
            cluster=ref.name,
            replicas=target.replicas,
            infra_env_kind=target.infra_env_kind,
            nodepool=target.nodepool,
        )
        event = {
            "user": user.username,
            "cluster": ref.name,
            "site": ref.site,
            "mce": ref.mce,
            "replicas": str(target.replicas),
            "target": target.nodepool or f"kind {target.infra_env_kind}",
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


def _refuse_locked(options: ScaleOptions, target: ScaleTarget) -> None:
    """A flavor's locked replicas move only back to their locked value (the user, 2026-11-16)."""
    if target.nodepool is not None:
        pool = next((p for p in options.nodepools if p.name == target.nodepool), None)
        if pool is None or pool.locked_replicas in (None, target.replicas):
            return  # a name the file lacks is the workflow's to refuse, in its words
        raise InvalidInputError(
            f"NodePool {pool.label} cannot be scaled",
            [
                f"{pool.label}: its replicas are locked by flavor {pool.locked_by} at "
                f"{pool.locked_replicas}; change the flavor, or restore it to "
                f"{pool.locked_replicas}"
            ],
        )
    kind = target.infra_env_kind or ""
    locked = [p for p in options.nodepools if belongs_to_kind(p.infra_env, kind) and p.locked_by]
    if locked:
        raise InvalidInputError(
            f"kind {kind} cannot be scaled",
            [
                f"{p.label}: kind {kind} selects it, and its replicas are locked by flavor "
                f"{p.locked_by} at {p.locked_replicas}; scale the other NodePools by name"
                for p in locked
            ],
        )


def _log(level: int, message: str, name: str, event: Mapping[str, str]) -> None:
    fields = " ".join(f"{key}={value}" for key, value in event.items())
    logger.log(level, "%s: %s", message, fields, extra={"event": name, **event})
