"""Who changes a NodePool's replicas while scaling is on (ADR-0062).

With ``DAY1_SCALE_NODEPOOLS`` the platform's update-nodepool workflow owns
the ``replicas`` of every NodePool a cluster file already has on ``main``:
it commits them to day1 ``main`` and has Argo CD apply them itself, and the
platform's rule is that NodePool replicas change only through it. Every
other write of the file keeps them as they are on ``main``:

- a person's YAML (the raw editor, an edit of a pending merge request) that
  changes one is refused: ``cluster_file.edit_problems`` applies
  :func:`replicas_problems`, the check every write of an existing cluster
  file passes;
- a change Wingman generates (a flavor's sync, a rollout's merge request)
  leaves them out of its merge request and lists the NodePools a person
  restores through update-nodepool instead (``SyncService.plan``).

Left alone: a new cluster (no file on ``main``), a ``nodepool[]`` entry that
is not on ``main`` yet (its first replicas), and removing an entry.
:func:`replicas_changes` is the one rule both use. With the setting off,
nothing here is applied.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

REPLICAS_BY_SCALE: Final = "NodePool replicas change through Scale on the cluster's Nodes tab"
DEFAULT_REPLICAS: Final = 1
"""What the chart renders for an entry without ``replicas``."""


@dataclass(frozen=True, slots=True)
class ReplicasChange:
    """A NodePool that is on ``main`` and whose replicas a write changes."""

    key: str
    """How it is matched with ``main``: its ``name``, else its ``infraEnvName``, else ``#<i>``."""
    index: int
    """Its position in the written file (``nodepool[<index>]``)."""
    main: object
    """Its replicas on ``main``, as the chart reads them (1 when the key is absent)."""
    written: object
    """Its replicas in the write."""


def replicas_changes(
    main: Mapping[str, object], written: Mapping[str, object]
) -> tuple[ReplicasChange, ...]:
    """Each NodePool on ``main`` whose replicas ``written`` changes (both parsed values files).

    An entry new in ``written`` and an entry ``written`` no longer has are not
    changes; neither is writing ``replicas: 1`` where ``main`` had none (the
    chart's default) or removing a ``replicas: 1``.
    """
    before = _replicas(main.get("nodepool"))
    return tuple(
        ReplicasChange(key=key, index=index, main=before[key][1], written=replicas)
        for key, (index, replicas) in _replicas(written.get("nodepool")).items()
        if key in before and before[key][1] != replicas
    )


def replicas_problems(main: Mapping[str, object], written: Mapping[str, object]) -> list[str]:
    """Why a person's write may not be proposed: each changed replicas, pointing to Scale."""
    return [
        f"nodepool {c.key} replicas: {c.main} → {c.written}. {REPLICAS_BY_SCALE}"
        for c in replicas_changes(main, written)
    ]


def _replicas(pools: object) -> dict[str, tuple[int, object]]:
    """Each entry's position and replicas, by its key; the first entry wins a key used twice."""
    found: dict[str, tuple[int, object]] = {}
    if not isinstance(pools, Sequence) or isinstance(pools, str):
        return found
    for index, pool in enumerate(cast("Sequence[object]", pools)):
        if not isinstance(pool, Mapping):
            continue
        entry = cast("Mapping[str, object]", pool)
        key = entry.get("name") or entry.get("infraEnvName") or f"#{index}"
        found.setdefault(str(key), (index, entry.get("replicas", DEFAULT_REPLICAS)))
    return found
