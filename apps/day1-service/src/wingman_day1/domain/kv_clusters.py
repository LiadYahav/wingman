"""What a KV cluster's file says about its place in its zone (ADR-0067's 2026-11-24 amendment).

A KV cluster is a hosted cluster on its zone's seed whose bare-metal workers
host the tenants' VMs (ADR-0067). The platform's create-vm places a VM on a
zone's KV clusters first fit, oldest first by the name's id letter (AD33),
and learns a KV cluster's zone **only** from its NodePools' ``nodeLabels``:

- a KV cluster whose NodePools name no zone, or a zone other than the one in
  its name, "is never offered to placement" (kubevirt-workflows
  ``docs/naming-convention.md`` §3, acceptance P1 criterion 5), so day1 flags
  it: :func:`kv_zone_problems`;
- a KV cluster holds at most ``maxNodes`` workers (``kv-capacity-controller.md``
  §3), the sum of its NodePools' ``replicas``: :func:`kv_workers`.

Pure: what the file says, never the hub's live count.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from wingman_day1.domain.cluster_file import NodePoolValues

ZONE_LABEL: Final = "topology.kubernetes.io/zone"
"""The node label a KV cluster's NodePools stamp on its hypervisors; create-vm reads it."""
MAX_KV_WORKERS: Final = 40
"""The capacity policy's ``maxNodes``: the hard size of a KV cluster (AD31)."""


def kv_workers(nodepools: Sequence[NodePoolValues]) -> int:
    """The workers the file asks for: every NodePool's ``replicas`` (none counts 0)."""
    return sum(pool.replicas or 0 for pool in nodepools)


def _where(index: int, pool: NodePoolValues) -> str:
    return f"nodepool[{index}] ({pool.infra_env_name or pool.name or 'unnamed'})"


def kv_zone_problems(zone: str | None, nodepools: Sequence[NodePoolValues]) -> list[str]:
    """Why create-vm would never place a VM on this KV cluster; empty when it would.

    Every NodePool must name ``zone``, the zone in the cluster's name, in its
    ``nodeLabels``. A name that gives no zone (off the convention) has
    nothing to compare: its NodePools must then name one zone between them.
    """
    if not nodepools:
        return ["it has no NodePool, so it names no zone"]
    problems: list[str] = []
    named: set[str] = set()
    for index, pool in enumerate(nodepools):
        value = pool.node_labels.get(ZONE_LABEL)
        if value is None or value == "":
            problems.append(
                f"{_where(index, pool)} names no zone: its nodeLabels have no {ZONE_LABEL}"
            )
        elif zone is not None and str(value) != zone:
            problems.append(
                f"{_where(index, pool)} names zone {str(value)!r}, not {zone!r} as the "
                "cluster's name does"
            )
        else:
            named.add(str(value))
    if zone is None and len(named) > 1:
        problems.append(f"its NodePools name several zones ({', '.join(sorted(named))}): one only")
    return problems
