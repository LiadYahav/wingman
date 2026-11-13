"""The bodies of ``/clusters/{name}/sync``: a cluster synced to its flavor (ADR-0037)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from wingman_day1.api.v1.schemas import (
    AddonDriftOut,
    NodepoolRefOut,
    ValueDriftOut,
    VersionDifferenceOut,
    _In,
)
from wingman_day1.application.sync import SyncPlan


class HardwareChoiceIn(_In):
    """A person's choice of network hardware for a nodepool whose own cannot be read."""

    nodepool: int = Field(ge=0, lt=100)
    """The nodepool's position in the file (``nodepool[i]``)."""
    hardware: str = Field(min_length=1, max_length=63)
    """A type from ``GET /machine-configs``; the file gets ``nm-conf-<clusterName>-<hw>``."""


class ConfigRemovalIn(_In):
    """A config the sync removes, confirmed by the person who asked for it."""

    nodepool: int = Field(ge=0, lt=100)
    name: str = Field(min_length=1, max_length=253)


class SyncPreviewIn(_In):
    """``POST /clusters/{name}/sync/preview``: the hardware choices, if drift needs them."""

    hardware: list[HardwareChoiceIn] = Field(default_factory=list, max_length=100)


class SyncIn(SyncPreviewIn):
    """``POST /clusters/{name}/sync``: what the preview showed, and the removals confirmed."""

    last_commit_id: str = Field(min_length=7, max_length=64)
    """The preview's: a file that changed since fails the sync."""
    spec_version: str = Field(min_length=1, max_length=64)
    """The flavor version the preview showed."""
    confirm_removals: list[ConfigRemovalIn] = Field(default_factory=list, max_length=1000)
    """Exactly the preview's ``removals``: the sync is refused otherwise."""


class ConfigRemovalOut(BaseModel):
    """A config a sync removes from a nodepool."""

    nodepool: NodepoolRefOut
    name: str


class RebootingOut(BaseModel):
    """A nodepool whose configs a sync changes: merging rolls its nodes."""

    nodepool: NodepoolRefOut
    replicas: int | None
    upgrade_type: str | None
    """The nodepool's ``upgradeType``; ``null`` when unset (the chart's ``InPlace``)."""
    max_unavailable: int | str | None
    """The nodepool's ``inPlace.maxUnavailable``; ``null`` when unset (one node at a time)."""
    replaces_nodes: bool
    """``upgradeType: Replace``: new nodes are provisioned and the old ones removed."""


class SyncPreviewOut(BaseModel):
    """``POST /clusters/{name}/sync/preview``: what syncing the cluster to its flavor would do."""

    cluster: str
    site: str
    mce: str
    path: str
    last_commit_id: str
    """Send it back with the sync."""
    spec_name: str
    spec_version: str
    """The flavor's current version; send it back with the sync."""
    file_spec_version: str | None
    """The version the file's header names now."""
    changes: list[ValueDriftOut]
    """Every locked value the file does not hold, with the hardware choices applied."""
    diff: str
    """The cluster file change, as a unified diff (empty when nothing changes)."""
    removals: list[ConfigRemovalOut]
    """Configs the sync removes; send each back in ``confirm_removals``."""
    rebooting: list[RebootingOut]
    """Nodepools whose configs change: merging reboots their nodes, rolling."""
    problems: list[str]
    """Why the sync cannot run now: a decision a person must make, a layout Wingman can't edit."""
    warnings: list[str]
    """Worth checking before merging; they do not block the sync."""
    can_sync: bool
    """No problems, and the file changes."""
    addons_to_install: list[AddonDriftOut]
    """Missing add-ons: not in the day1 MR; install them through day2."""
    version_differences: list[VersionDifferenceOut]
    addons_error: str | None
    """Set when day2 did not answer: missing add-ons are unknown."""

    @classmethod
    def of(cls, plan: SyncPlan) -> SyncPreviewOut:
        """From a sync plan."""
        ref = plan.cluster.ref

        def pool(index: int, name: str) -> NodepoolRefOut:
            return NodepoolRefOut(index=index, name=name)

        return cls(
            cluster=ref.name,
            site=ref.site,
            mce=ref.mce,
            path=str(ref.path),
            last_commit_id=plan.cluster.last_commit_id,
            spec_name=plan.spec.metadata.name,
            spec_version=plan.spec.metadata.version,
            file_spec_version=plan.cluster.provenance.spec_version,
            changes=[ValueDriftOut.of(d) for d in plan.changes],
            diff=plan.diff,
            removals=[
                ConfigRemovalOut(nodepool=pool(r.nodepool.index, r.nodepool.name), name=r.name)
                for r in plan.removals
            ],
            rebooting=[
                RebootingOut(
                    nodepool=pool(r.nodepool.index, r.nodepool.name),
                    replicas=r.replicas,
                    upgrade_type=r.upgrade_type,
                    max_unavailable=r.max_unavailable,
                    replaces_nodes=r.replaces_nodes,
                )
                for r in plan.rebooting
            ],
            problems=list(plan.problems),
            warnings=list(plan.warnings),
            can_sync=not plan.problems and plan.changes_file,
            addons_to_install=[AddonDriftOut.of(a) for a in plan.addons_to_install],
            version_differences=[VersionDifferenceOut.of(d) for d in plan.version_differences],
            addons_error=plan.addons_error,
        )
