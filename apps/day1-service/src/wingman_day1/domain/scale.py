"""A hosted cluster's NodePools scaled through the platform's update-nodepool workflow (ADR-0062).

The workflow owns the scale: it reads the cluster's NodePools in day1 and on
the MCE (they must agree), plans the new replicas, commits them to day1
``main`` itself, has Argo CD apply that commit and checks that the NodePools
show it; on a scale-down the servers named leave, else those a policy ranks
first: the run's own, else the NodePool's (``scale_down_policy``; see
``docs/notes/2026-11-16-scale-nodepools-api.md``).
Wingman starts a run and shows it. Only data crosses back: these types hold
the workflow's strings as it gives them, and there is no phase list.

A run sets one NodePool, named (the workflow refuses anything else since
2026-11-18). The one thing Wingman works out itself is that name, which the
cluster file gives by the chart's rule (``name``, else
``<clusterName>-<InfraEnv>``), the rule the workflow matches day1 with the MCE
by: day1 refuses a start it cannot map to one NodePool of the file. A run
recorded by InfraEnv kind before then is still read and shown as it is.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from wingman_day1.domain.locks import MISSING, Lock, cluster_file_key
from wingman_day1.domain.replicas_ownership import replicas_changes
from wingman_day1.domain.scale_down_policy import policy_of
from wingman_day1.domain.value_drift import ValueDrift, show_value

SCALE_WORKFLOW_PREFIX: Final = "update-nodepool-"
"""A cluster's run is ``update-nodepool-<file stem>``, one at a time (the orchestrator's id)."""
DEFAULT_REPLICAS: Final = 1
"""What the chart renders for a ``nodepool[]`` entry without ``replicas``."""
_ERROR_TYPE: Final = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Error|Exception)):\s")


def scale_workflow_id(stem: str) -> str:
    """The id of the update-nodepool run for the cluster file ``<stem>.yaml``."""
    return f"{SCALE_WORKFLOW_PREFIX}{stem}"


@dataclass(frozen=True, slots=True)
class ScaleRequest:
    """One start: one NodePool of the cluster, by name, and its replicas, set exactly."""

    mce_cluster: str
    cluster: str
    """The cluster file's stem: the workflow's ``cluster``."""
    replicas: int
    nodepool: str
    server_names: tuple[str, ...] = ()
    """A scale-down's servers that leave, exactly as many as it removes; empty: a policy (or
    CAPI) picks. Never on a scale-up."""
    scale_down_policy: str | None = None
    """A scale-down's policy for this run only, ahead of the NodePool's own; never with
    ``server_names``, never on a scale-up."""


# ── A run, as the orchestrator reports it ────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ScaleChild:
    """The scale-up-nodepool or scale-down-nodepool run the parent waits for."""

    workflow_id: str
    status: str | None = None
    """``None`` when the child could not be read."""
    phase: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class NodePoolChange:
    """One NodePool the run selected: its replicas before and after, as the workflow planned."""

    name: str
    infra_env: str | None = None
    before: int | None = None
    after: int | None = None
    scale_down_policy: str | None = None


@dataclass(frozen=True, slots=True)
class LiveReplicas:
    """One NodePool as the run read it back on the MCE after the sync."""

    name: str
    replicas: int | None = None
    ready_replicas: int | None = None


@dataclass(frozen=True, slots=True)
class ChosenServer:
    """A server a scale-down chose to leave, by its NodePool's policy or by name, and why."""

    nodepool: str
    machine: str
    node: str | None
    policy: str
    """The policy's name; ``named`` for a server the request named."""
    reason: str
    server: str | None = None
    """The server, lowercased, when the request named it."""


@dataclass(frozen=True, slots=True)
class ScaleResult:
    """What a completed run did: its NodePools before and after, and its child's result."""

    direction: str
    """``up``, ``down`` or ``none`` (the replicas were already the request: nothing written)."""
    infra_env_kind: str | None = None
    """Set only on a run recorded by kind before 2026-11-18; ``nodepool`` on every other."""
    nodepool: str | None = None
    day1_path: str | None = None
    total_before: int | None = None
    total_after: int | None = None
    nodepools: tuple[NodePoolChange, ...] = ()
    child_workflow_id: str | None = None
    revision: str | None = None
    """The day1 commit (main's head when ``committed`` is false: a re-run found it there)."""
    committed: bool | None = None
    live: tuple[LiveReplicas, ...] = ()
    chosen: tuple[ChosenServer, ...] = ()
    deleting: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()
    """What the request said about a scale-down that a run not scaling down had no use for."""


@dataclass(frozen=True, slots=True)
class ScaleRun:
    """An update-nodepool run: status, the workflow's phase, its child, result or error."""

    workflow_id: str
    status: str
    """The orchestrator's status, lowercase: ``running``, ``completed``, ``failed``, ..."""
    phase: str | None = None
    direction: str | None = None
    child: ScaleChild | None = None
    result: ScaleResult | None = None
    error: str | None = None
    """Why it failed, in the workflow's words."""

    @property
    def cluster(self) -> str:
        """The cluster file's stem the run scales."""
        return self.workflow_id.removeprefix(SCALE_WORKFLOW_PREFIX)

    @property
    def error_type(self) -> str | None:
        """The failure's type when its words name one (a child's: ``<Type>: <message>``)."""
        return error_type(self.error)


def error_type(error: str | None) -> str | None:
    """The first ``<Name>Error: `` in a run's error; ``None`` when the words name none."""
    found = _ERROR_TYPE.search(error or "")
    return found.group(1) if found else None


# ── The cluster file's NodePools, for the page and its guards ────────────────


@dataclass(frozen=True, slots=True)
class FileNodePool:
    """One ``nodepool[]`` entry of the cluster file on ``main``."""

    index: int
    name: str | None
    """The NodePool update-nodepool takes by name; ``None`` when the file cannot name it."""
    infra_env: str | None
    replicas: int | None
    """As the chart renders it: the entry's, else 1; ``None`` when it is not a whole number."""
    locked_replicas: int | None = None
    """The replicas a flavor locks this NodePool to; ``None`` when none does."""
    locked_by: str | None = None
    """That flavor."""
    scale_down_policy: str | None = None
    """The entry's ``redbull.io/scale-down-policy`` annotation as written; ``None`` without one."""

    @property
    def label(self) -> str:
        """Its name, else its position."""
        return self.name or f"nodepool[{self.index}]"

    @property
    def unnamed(self) -> str | None:
        """Why it cannot be scaled by name; ``None`` when it can."""
        if self.name is not None:
            return None
        return (
            f"{self.label} has neither name nor infraEnvName, so its NodePool cannot be named "
            "from the file"
        )


def infra_env_of(entry: Mapping[str, object]) -> str | None:
    """The InfraEnv an entry takes Agents from: ``infraEnvName``, else its selector's label."""
    selector = entry.get("agentLabelSelector")
    label = None
    if isinstance(selector, Mapping):
        label = cast("Mapping[str, object]", selector).get("nodeLabelValue")
    found = entry.get("infraEnvName") or label
    return str(found) if found else None


def scale_name(entry: Mapping[str, object], *, cluster_name: str) -> str | None:
    """The NodePool the chart renders: ``name``, else ``<clusterName>-<InfraEnv>``, else ``None``.

    The rule update-nodepool matches a day1 entry with the MCE's NodePool by.
    """
    if entry.get("name"):
        return str(entry["name"])
    infra_env = infra_env_of(entry)
    return f"{cluster_name}-{infra_env}" if infra_env else None


def replicas_locks(locks: Sequence[Lock]) -> dict[int, int]:
    """The flavor's locked replicas by NodePool position (``nodepools[<i>].replicas``)."""
    found: dict[int, int] = {}
    for lock in locks:
        key = cluster_file_key(lock.path)
        if key is None or len(key.segments) != 3 or key.segments[2] != "replicas":
            continue
        index, value = key.segments[1], lock.value
        if isinstance(index, int) and isinstance(value, int) and not isinstance(value, bool):
            found[index] = value
    return found


def file_nodepools(
    values: Mapping[str, object],
    *,
    cluster_name: str,
    locked: Mapping[int, int] | None = None,
    flavor: str | None = None,
) -> tuple[FileNodePool, ...]:
    """The file's NodePools with their names, InfraEnvs, replicas and the flavor's locks."""
    raw = values.get("nodepool")
    entries = cast("Sequence[object]", raw) if isinstance(raw, list) else []
    locked = locked or {}
    pools: list[FileNodePool] = []
    for index, item in enumerate(entries):
        if not isinstance(item, Mapping):
            continue
        entry = cast("Mapping[str, object]", item)
        lock = locked.get(index)
        pools.append(
            FileNodePool(
                index=index,
                name=scale_name(entry, cluster_name=cluster_name),
                infra_env=infra_env_of(entry),
                replicas=_replicas(entry),
                locked_replicas=lock,
                locked_by=flavor if lock is not None else None,
                scale_down_policy=policy_of(entry),
            )
        )
    return tuple(pools)


def _replicas(entry: Mapping[str, object]) -> int | None:
    value = entry.get("replicas", DEFAULT_REPLICAS)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# ── A flavor's sync that leaves replicas to update-nodepool ──────────────────


@dataclass(frozen=True, slots=True)
class HeldReplicas:
    """A NodePool whose drifted locked replicas a sync leaves out, for update-nodepool."""

    index: int
    name: str | None
    """The NodePool to restore by name; ``None`` when the file cannot name it."""
    replicas: object
    """Its replicas on ``main``."""
    flavor_replicas: object
    """The flavor's locked value: what a restore sets."""


def held_back(
    main: Mapping[str, object],
    written: Mapping[str, object],
    drift: Sequence[ValueDrift],
    *,
    cluster_name: str,
) -> tuple[tuple[ValueDrift, ...], tuple[HeldReplicas, ...]]:
    """The drift a flavor's sync writes, and the replicas it leaves to update-nodepool.

    ``written`` is the file the whole ``drift`` would make of ``main``. Each
    NodePool on ``main`` whose replicas it changes (``replicas_changes``, the
    rule every write of the file follows) keeps them: its replicas drift is
    held back, for a person to restore through update-nodepool.
    """
    moved = {c.index for c in replicas_changes(main, written)}
    held = [
        d
        for d in drift
        if d.nodepool is not None
        and d.nodepool.index in moved
        and d.file_key.segments[-1] == "replicas"
    ]
    names = {p.index: p.name for p in file_nodepools(main, cluster_name=cluster_name)}
    return tuple(d for d in drift if all(d is not h for h in held)), tuple(
        HeldReplicas(
            index=d.nodepool.index,
            name=names.get(d.nodepool.index),
            replicas=DEFAULT_REPLICAS if d.cluster_value is MISSING else d.cluster_value,
            flavor_replicas=d.flavor_value,
        )
        for d in held
        if d.nodepool is not None
    )


def restore_lines(held: Sequence[HeldReplicas]) -> list[str]:
    """One line per NodePool whose replicas a person restores through update-nodepool."""
    return [
        f"nodepool `{h.name or f'nodepool[{h.index}]'}` replicas {show_value(h.replicas)} → "
        f"{show_value(h.flavor_replicas)}: restore it with update-nodepool (Scale, Nodes tab)"
        for h in held
    ]
